import os     #Python 自带的标准库模块，提供访问操作系统相关功能的接口。
from openai import OpenAI
import json
import uuid
import time
import rclpy
from std_msgs.msg import String
from pydantic import ValidationError
from robot_agent.agent.action_validator import validate_action,load_locations
import subprocess
from robot_agent.agent.tool_registry import ToolRegistry


def navigate_handler(validated):
    target=validated.target

    command=f"go to {target}"
    #为这次任务创建唯一的编号
    task_id=uuid.uuid4().hex

    payload={
        "command":command,
        "task_id":task_id
    }
    #转换为JSON字符串
    command_json=json.dumps(payload)   #Python 对象 → JSON 字符串
    #包装成ros2 std_msgs/msg/String消息
    ros_message=json.dumps({"data": command_json})

    rclpy.init()
    node=rclpy.create_node("deepseek_result_listener")
    result_holder={"data": None}

    def result_callback(msg):
        try:
            data=json.loads(msg.data)
        except:
            print("收到无法解析的命令")
            return
        if not isinstance(data,dict):   #判断对象对象类型
            return
        if data.get("task_id")==task_id:
            result_holder['data']=data
            print("收到当前任务的导航结果")
#创建订阅者，只是告诉 ROS2 收到消息时应该调用哪个函数；但要真正运行这个回调，还需要 ROS2 的 Executor（执行器）处理它。
    subscription=node.create_subscription(
        String,
        "/agent/task_result",
        result_callback,
        10
    )

    try:
        ready_deadline=time.monotonic()+10

        while node.count_publishers("/agent/task_result")==0:         #查询发布者的数量
            if time.monotonic()>=ready_deadline:
                raise RuntimeError("RobotAgent未启动或Topic不可用")
        
        print("准备发送 ROS2指令:",command)
        print("任务编号：",task_id)
        print("发送的消息:", ros_message)
#是 Python 标准库提供的功能;它可以让 Python 程序启动并执行一个外部命令。
        subprocess.run(
        [
            "ros2",
            "topic",
            "pub",
            "--once",
            "/agent/command",
            "std_msgs/msg/String",
            ros_message

        ],
        #如果外部命令以非零退出码结束，就抛出 CalledProcessError 异常
        check=True,
        timeout=20
    )
        print("导航指令已发布，等待机器人完成...")

        # 最多等待 180 秒
        deadline = time.monotonic() + 180

        while result_holder["data"] is None:
            if time.monotonic() >= deadline:
                return {
                    "status": "timeout",
                    "success": None,
                    "target": target,
                    "task_id": task_id
                }

            rclpy.spin_once(node, timeout_sec=0.5)      #让ros处理一次回调

        # 返回真实导航结果
        return result_holder["data"]

    finally:
        node.destroy_node()
        rclpy.shutdown()

#创建ToolRegister实例
registry=ToolRegistry()

#注册导航工具
registry.register(
    "navigate_to_location",
    navigate_handler
)

# 1.创建Deepseek API 客户端
client=OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com", #用于指定请求发送到哪个服务器
    timeout=30.0 #表示单次请求操作的超时配置为 30 秒
)
# 2.定义机器人可以使用的工具
# JSON Schema 规范中有特定含义的关键字
allowed_locations=load_locations()
tools=[
    {
        "type":"function",
        "function":{
            "name":"navigate_to_location",
            "description":"Navigate robot to a known location",
            "parameters":{
                "type":"object",
                #定义参数有哪些字段
                "properties":{   
                    "target":{    
                    "type":"string",
                    "enum":allowed_locations#目标值应该来自指定集合
                }
            },
            "required":["target"],
            #不允许额外字段
            "additionalProperties":False
        }
    }
    }
]
print(
    "发送给DeepSeek的enum:",
    tools[0]["function"]["parameters"]["properties"]["target"]["enum"]
)
# 3.发送用户指令

while True:
    #从终端读取命令
    user_command=input("请输入机器人指令： ").strip()
    messages=[{
    "role":"system",
    "content": (
            "你是机器人助手，可以通过多轮对话确认导航需求。"
            "根据用户指令选择工具。"
            "工具执行后，必须根据真实执行结果回复。"
            "只有success为true才能说导航成功。"
            "如果结果超时或未知，不能说已经到达。"
        )
},
{
    "role": "user",
    "content": user_command
}]
    if user_command == "退出":
        break
    if not user_command:
        continue
    messages.append({
        "role": "user",
        "content": user_command
    })
    response=client.chat.completions.create(
    model="deepseek-flash",
    messages=messages,
    tools=tools, #当前机器人可供选择的工具列表
    tool_choice="auto", #允许模型自主判断是否需要调用工具
    extra_body={"thinking": {"type": "disabled"}}
)

# 4. 提取 DeepSeek 的返回消息
    message = response.choices[0].message
    if message.tool_calls:
        messages.append(
        message.model_dump(exclude_none=True)
    )

# 5. 查看模型是否选择了工具
#如果 DeepSeek 选择调用工具，你通常会看到：
# - message.content 可能是 None 或空内容。
# - message.tool_calls 包含工具名称、参数和工具调用 ID。
# 如果没有选择调用工具，你可能看到：
# - message.content 包含普通文字。
# - message.tool_calls 为 None。
# API 使用跨语言的数据交换格式 JSON

        for index,tool_call in enumerate(message.tool_calls):   #遍历列表时，同时获得元素的序号和元素本身。

          name = tool_call.function.name
          raw_arguments = tool_call.function.arguments

          print("工具名称:", name)
          print("原始参数:", raw_arguments)
  
          if index>0:
            result={  
                "status": "rejected",
                "success": False,
                "message": "当前版本每次只允许执行一个导航工具"

            }
          else:
            try:
                arguments = json.loads(raw_arguments)

                result = registry.execute(name, arguments)

            except (ValueError, subprocess.CalledProcessError,FileNotFoundError) as error:
                   result = {
                    "status": "error",
                    "success": None,
                    "message": str(error)
                }

          print("工具调用结果:",result)
          messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(result, ensure_ascii=False)
        })
        final_response = client.chat.completions.create(
        model="deepseek-flash",
        messages=messages,
        tools=tools,
        tool_choice="none",
        extra_body={"thinking": {"type": "disabled"}}
    )

        final_message = final_response.choices[0].message

        print("DeepSeek 最终回复:")
        print(final_message.content)
        break
    
    else:

        reply = message.content or ""

        print("DeepSeek 回复:", reply)

        messages.append({
            "role": "assistant",
            "content": reply
        })