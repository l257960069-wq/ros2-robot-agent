import rclpy
import time
import csv
import json
from pathlib import Path
from rclpy.node import Node
from std_msgs.msg import String
from rclpy.action import ActionClient
from robot_skills_interfaces.action import NavigateSkill


class RobotAgent(Node):
    def __init__(self):
        super().__init__('robot_agent')      #super() python 内置方法，调用父类初始化方法
        self.command_sub=self.create_subscription(        #命令接受
            String,
            '/agent/command',
            self.command_callback,
            10
        )
        #agent发布任务完成消息
        self.task_result_pub=self.create_publisher(
             String,
             '/agent/task_result',
             10
        )
        self._task_start_time=0.0
        self._last_feedback_time=0.0
        self._current_target = None #记录当前目标
        self._current_task_id=None
        self._agent_retry_count = 0 #agent重试次数
        self._retry_timer = None #保存等待的ROS2 Timer,便于取消和销毁
        self.get_logger().info('Robot Agent started')
        self._navigate_skill_client=ActionClient(
             self,
             NavigateSkill,
             '/navigate_skill'
        )
        #这里使用pathlib标准库，Path.home()的作用是返回当前用户的主目录，/ 被定义为拼接路径
        self._csv_path=(Path.home()
                        /'robot_agent_ws'
                        /'benchmark_result'
                        /'agent_runs.csv'
                        )
   
    def command_callback(self,msg):
        raw=msg.data.strip()
        task_id=None
            # Benchmark 发送的是 JSON 字符串
        if raw.startswith('{'):
           try:
            payload = json.loads(raw)
           except json.JSONDecodeError:
            self.get_logger().error('Invalid command JSON')
            return

           if not isinstance(payload, dict):
            self.get_logger().error('Invalid command format')
            return

           command = payload.get('command')
           task_id = payload.get('task_id')

           if not isinstance(command, str) or not isinstance(task_id, str) or not task_id:
            self.get_logger().error('Missing command or task_id')
            return

        else:
        # 保留原来的手动命令
           command = raw

        self.get_logger().info(f'Received command: {command}')

        task = self.parse_command(command)

        if task is None:
           self.get_logger().info(
            f'Cannot understand command: {command}'
        )
           return

        self.get_logger().info(f'Parsed task: {task}')

        if task['skill'] == 'navigate_to':

          if self._current_target is not None:
            self.get_logger().info(
                f'Agent is busy with {self._current_target}'
            )
            return

          self._current_target = task['target']
          self._current_task_id = task_id
          self._agent_retry_count = 0
          self._task_start_time = time.monotonic()

        self.send_navigate_goal(task['target'])
        
    def parse_command(self,command):
        command=command.lower().strip()
        if command=='go to kitchen':
            return{
                'skill':'navigate_to',
                'target':'kitchen'
            }
        if command=='go to room':
                    return{
                        'skill':'navigate_to',
                        'target':'room'
                    }
        if command=='go to unreachable':
           return {
                'skill':'navigate_to',
                'target':'unreachable'
           }
        if command == 'go to blocked':
           return {
        'skill': 'navigate_to',
        'target': 'blocked'
    }
        return None
    def send_navigate_goal(self,target):
        self.get_logger().info(f'Sending navigation skill goal:{target}')
        self._navigate_skill_client.wait_for_server()    #ROS2 ActionClient 的方法，阻塞当前代码停在这里，直到对应的 Action Server 出现。
        if not self._navigate_skill_client.wait_for_server(timeout_sec=1.0):
           self.get_logger().error('NavigateSkill server unavailable')
           self._current_target = None
           return
        goal_msg=NavigateSkill.Goal() #创建Action对象
        goal_msg.place=target    #给对象赋值

        self._send_goal_future=(
             self._navigate_skill_client.send_goal_async(goal_msg,
                                                         feedback_callback=self.navigation_feedback_callback)  #返回第一个future，send_goal_async() 是 ActionClient 的方法
        )
        self._send_goal_future.add_done_callback(        #.add_done_callback作用是注册“Future 完成后要调用的函数”
             self.navigation_goal_response_callback
        )

    def navigation_goal_response_callback(self,future):  #future代表ClientGoalHandle
        goal_handle=future.result()
        if not goal_handle.accepted:
             self.get_logger().info('NavigateSkill goal rejected')
             self._current_target=None
             return
        self.get_logger().info('NavigateSkill gaol accepted')

        self._get_result_future=goal_handle.get_result_async()  #返回第二个future，get_result_async() 是 ClientGoalHandle 的方法
        self._get_result_future.add_done_callback(
             self.navigation_result_callback
        )
        #Future.result() 不决定返回什么；创建这个 Future 的异步函数决定它最终装什么。
        #Future 不是“只装一个值的变量”，而是一个专门管理异步任务完成状态和结果的对象。
    def navigation_result_callback(self,future):
         result_response=future.result()
         result=result_response.result
         self.get_logger().info(
              f'Navigation Skill finished:'
              f'success={result.success}'
              f'message={result.message}'
              f'error_code={result.error_code}'
         )
         if result.success:
              self.get_logger().info(f'Agent decision:task succeeded')
              self.finish_task(result)
              return
         if result.error_code==103 and self._agent_retry_count<1:
              self._agent_retry_count+= 1
              self.get_logger().warning(f'Agent decision:test retry for errro_code={result.error_code},'
                                        'retry in  2 seconds')
              self._retry_timer=self.create_timer(2.0,self.retry_callback) #创建定时器，如果不做处理2秒触发一次
              return  #结束当前函数调用
         self.get_logger().warning(f'Agent decision:stop task,error_code={result.error_code}')
         self.finish_task(result)
    def retry_callback(self):
        #停止周期定时器，确保只重试一次
         self._retry_timer.cancel()
         self.destroy_timer(self._retry_timer)
         self._retry_timer=None
         self.get_logger.info(f'Agent decision navigation to{self._current_target}')
         self.send_navigate_goal(self._current_target)
    def navigation_feedback_callback(self,feedback_msg):
         feedback=feedback_msg.feedback
         now=time.monotonic()
         if now-self._last_feedback_time<1.0:
              return
         self._last_feedback_time=now
         self.get_logger().info(f'Didstance remaining:{feedback.distance_remaining:.2f} m'
                                f'Nav2 recoveries:{feedback.nav2_recoveries}'
                                )
    
    def finish_task(self,result):
         duration=time.monotonic()-self._task_start_time
         #定义一个列表
         fields=[
              'target',
              'success',
              'duration_s',
              'error_code',
              'agent_retries'
         ]
         #定义一个字典
         row={
              'target':self._current_target,
              'success':result.success,
              'duration_s':round(duration,2),#四舍五入取两位数
              'error_code':result.error_code,
              'agent_retries':self._agent_retry_count
             }
        #异常和中断操作
         try:
            #.parent获取文件所在的文件夹，.mkdir()是创建文件夹
            self._csv_path.parent.mkdir(
              parents=True,
              exist_ok=True
         )
             # 判断 CSV 是否需要写入表头
            is_new = (
            not self._csv_path.exists()
            or self._csv_path.stat().st_size == 0
        )
        #with ... as f 表示进入一个文件操作上下文，并把打开的文件对象赋给 f，创建对象不代表完全不需要参数
            with self._csv_path.open(
            'a',
            newline='',
            encoding='utf-8'
        ) as f:

              writer = csv.DictWriter(
                f,
                fieldnames=fields #CSV 列名和列顺序
            )

              if is_new:
                writer.writeheader()

              writer.writerow(row)

              self.get_logger().info(
            f'Benchmark record saved: {row}'
        )

         except OSError as exc:
               self.get_logger().error(
            f'Failed to save benchmark record: {exc}'
        )

         finally:
             completed_task_id=self._current_task_id
        # 无论文件保存是否成功，都要释放 Agent 状态
             self._current_target = None
             self._task_start_time = None
             self._current_task_id=None
             
             # 在原来的 row 基础上增加 task_id
             #**row 表示把 row 字典中的所有键值对展开到新字典中，然后额外加入一个 task_id
             result_payload = {
               **row,
               'task_id': completed_task_id
               }
             task_result_msg=String()
             task_result_msg.data=json.dumps(result_payload) #把 Python 字典转换成 JSON 格式的字符串
             self.task_result_pub.publish(task_result_msg)
             self.get_logger().info(f'Task result published:{task_result_msg.data}')
                 

         
def main(args=None):
        rclpy.init(args=args)
        node=RobotAgent()

        rclpy.spin(node)  #括号内传入需要一直持续运行的节点对象
        node.destroy_node()
        rclpy.shutdown()

if __name__=='__main__':
       main()