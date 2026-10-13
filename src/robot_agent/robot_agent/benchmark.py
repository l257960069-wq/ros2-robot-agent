import json
import time
import rclpy
import uuid
from rclpy.node import Node
from std_msgs.msg import String


class Robotbenchmark(Node):
    def __init__(self):
        super().__init__('robot_benchmark')

        #向agent发送命令
        self.command_pub=self.create_publisher(
            String,
            '/agent/command',
            10
        )
        #接受agent的最终任务结果
        self.result_sub=self.create_subscription(
            String,
            '/agent/task_result',
            self.result_callback,
            10
        )
        self.current_target=None 
        self.last_result= None
        self.current_task_id=None
    def result_callback(self,msg):
        try:
            result=json.loads(msg.data) #把字符串转换回 Python 字典
        except json.JSONDecodeError:
            self.get_logger().error('Invild JSON task result')
            return
        if self.current_target is None:
            return
        if result.get('target')!=self.current_target:
            return 
        if result.get('task_id')!=self.current_task_id:
             self.get_logger().warning('Ignored result with mismatched task_id')
             return 
        self.last_result=result
    def wait_for_agent(self):
            deadline=time.monotonic()+10.0
            while rclpy.ok():
                command_ready=(
                self.command_pub.get_subscription_count()>0 #检查命令 Topic 是否有订阅者
                )           
                result_ready=(
                    self.result_sub.get_publisher_count()>0 #检查结果 Topic 是否有发布者
                )
                if command_ready and result_ready:
                    return
                if time.monotonic()>deadline:
                    raise TimeoutError('Agent topics not ready'
                                       f'command_ready={command_ready},'
                                       f'result_ready={result_ready}') #raise主动抛出异常
                rclpy.spin_once(self,timeout_sec=0.2)
    def run_once(self,target):
        self.current_target=target 
        self.current_task_id=uuid.uuid4().hex
        self.last_result=None
        msg=String()
        payload={
             'command':f'go to {target}',
             'task_id':self.current_task_id
        }
        msg.data=json.dumps(payload)
        self.get_logger().info(
    f'Benchmark sending task_id: {self.current_task_id}'
)
        self.get_logger().info(f'Sending task:{target}')
        self.command_pub.publish(msg)

        deadline=time.monotonic()+120.0
        while rclpy.ok() and self.last_result is None:
            if time.monotonic()>=deadline:
                self.current_target=None
                raise TimeoutError(f'Task timed out:{target}'
                                   )
            rclpy.spin_once(self,timeout_sec=0.2)
        if not rclpy.ok():
                raise RuntimeError(f'ROS2 stopping')
        result=self.last_result
        self.current_target=None
        return result 
def main(args=None):
            rclpy.init(args=args)
            node = Robotbenchmark()

            # 第一次先运行两个任务
            targets =['kitchen','room']*5+['blocked']*2
            records = [] #保存测试结果的列表

            try:
              node.wait_for_agent()

              for index, target in enumerate(targets, start=1): #enumerate() 同时提供编号和元素,编号从1开始

                 node.get_logger().info(
                f'Trial {index}/{len(targets)}: {target}'
            )

                 result = node.run_once(target)
                 records.append(result)

                 node.get_logger().info(
                f'Completed: {result}'
            )

               # 所有任务完成后，计算统计指标
              total = len(records)

              successes = sum(
            1 for record in records
            if record['success']
        )

              success_rate = successes / total * 100

              average_duration = sum(
              record['duration_s'] for record in records
        ) / total

              node.get_logger().info(
            f'Benchmark finished: '
            f'total={total}, '
            f'success_rate={success_rate:.1f}%, '
            f'average_duration={average_duration:.2f}s'
        )

              
              normal_records=[
                   r for r in records
                   if r['target'] in ('kitchen','room')
              ]

              blocked_records=[
                   r for r in records    #r把什么放进新列表里，for r in...遍历列表
                   if r['target']=='blocked' #哪些纪录可以保留
              ]
              normal_successes=sum(
                   1 for r in normal_records if r['success']
              )
              if normal_records:
                   normal_success_rate=(
                        normal_successes/len(normal_records)*100
                   )
                   normal_avg_duration=sum(
                        r['duration_s'] for r in normal_records
                   )/len(normal_records)
                   node.get_logger().info(
                        f'Normal navigation:'
                        f'{normal_successes}/{len(normal_records)} succeeded,'
                        f'success_rate={normal_success_rate:.1f}%,'
                        f'avgerage_duration={normal_avg_duration:.2f}s'
                   )
              if blocked_records:
                   detected_failures=sum(
                        1 for r in blocked_records
                        if not r['success']and r['error_code']==208
                   )
                   node.get_logger().info(
                        f'Blocked scenario:'
                        f'{detected_failures}/{len(blocked_records)}'
                        f'returned expected error 208'
                   )
            except (TimeoutError, RuntimeError) as exc:
                node.get_logger().error(str(exc))

            except KeyboardInterrupt:
                node.get_logger().info('Benchmark interrupted')

            finally:
                node.destroy_node()

                if rclpy.ok():
                   rclpy.shutdown()
                                       

if __name__ == '__main__':
    main()