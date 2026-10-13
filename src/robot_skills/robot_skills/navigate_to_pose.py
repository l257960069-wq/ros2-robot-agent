import rclpy      #导入ROS2的Python库
import math       #导入数学库
import time       #程序进行的时间
from rclpy import Future
from std_msgs.msg import String #std_msgs/msg/String data字段
from rclpy.action import ActionClient, ActionServer #拿出ROS2的ActionClient
from  nav2_msgs.action import NavigateToPose #引入Action类
from rclpy.node import Node    #从rclpy.node导入node类
from action_msgs.msg import GoalStatus
from nav2_msgs.action import ComputePathToPose
from robot_skills_interfaces.action import NavigateSkill 
class NavigateToPoseSkill(Node): #定义一种对象类型，继承ROS2的node
   def __init__(self):             #定义一个函数，__init__特殊函数创建对象时自动执行；self是创建的对象在初始化完成之后传给node
     super ().__init__('navigate_to_pose_skill')#初始化node,节点的名字：navigate_to_pose
     self.command_sub=self.create_subscription(           #创建ROS2 Topic订阅者，属性保存订阅者对象 
        String,           #消息类型
        '/robot_skill/navigate',#topic名字
        self.command_callback,#收到消息以后，要调用哪个方法处理
        10                    #关于ROS的通讯质量
     )
     self.get_logger().info('NavigateToPose Skill started')#调用创建对象的get_logger方法输出日志

     self._action_server=   ActionServer(self,
                                         NavigateSkill,
                                         '/navigate_skill' , #运行时创建一个具体的action接口的名字，文件不需要提前存在，agent的名字
                                         self.execute_navigate_skill   #也是一种callback
     )


     self._action_client=   ActionClient(self,             #前面的'_'
                                        #  是一种命名规则：表示这个成员给类内部使用；
                                         NavigateToPose,#创建一个ActionClient (属于那一个node，action类型,连接的Action Server)
                                         '/navigate_to_pose')# NAV2的名字
     
     self.get_logger().info('Waiting for /navigate_to_pose action server...')
     self._action_client.wait_for_server() #等待对应的action server
     self.get_logger().info('/navigate_to_pose action server in already')    #打印日志 
     self.locations={'kitchen':(2.0,1.0,0.0),                                #创建字典
                      'unreachable': (100.0, 100.0, 0.0),
                      'blocked': (2.3794236, 2.16840243, -0.00143432617),
                      'room':(0.8777634,-1.75424587,-0.0092468)}
     self.max_retries= 1
     self.task_active = False
     self._skill_done_future=None 
     self._skill_goal_handle=None

   def command_callback(self,msg):    #msg是自己定义的参数变量
          place=msg.data.strip()   #局部变量
    
          self.get_logger().info(
             f'Received navigation command:{place}'
          )
          self.navigate(place)

   def navigate(self,place):

      if place not in self.locations:
         self.get_logger().error(f'Unknown location: {place}')
         return
      
      if self.task_active:
          self.get_logger().info(
              f'Navigation task already active ,ignoring:{place}'
          )
          return
      self.retry_count= 0
      self.feedback_count = 0
      self.nav2_recoveries = 0 
      self.task_start_time = time.monotonic()
      self.task_active=True
      x,y,yaw=self.locations[place]
      self.current_place=place
      self.current_goal=(x,y,yaw)
      self.navigate_to_pose(x,y,yaw)

     #初始化Goal
   def navigate_to_pose(self,x,y,yaw):
     goal_msg=NavigateToPose.Goal()
     goal_msg.pose.header.frame_id='map'
     goal_msg.pose.pose.position.x=x
     goal_msg.pose.pose.position.y=y
     goal_msg.pose.pose.position.z=0.0

     goal_msg.pose.pose.orientation.x =0.0
     goal_msg.pose.pose.orientation.y =0.0
     goal_msg.pose.pose.orientation.z = math.sin(yaw / 2.0)
     goal_msg.pose.pose.orientation.w = math.cos(yaw / 2.0)
     #把 Goal 发给 /navigate_to_pose
     self._send_goal_future=self._action_client.send_goal_async(goal_msg,feedback_callback=self.feedback_callback) #异步发送，执行后返回一个future，收到Goal的Feedback时执行提供的方法
     self._send_goal_future.add_done_callback(
        self.goal_response_callback
     )#调用future自己的add_done_callback()方法，Future 完成时，会把 Future 对象本身传给回调函数

     #/navigateskill server

   def goal_response_callback(self,future):     #self表明操作对象
           goal_handle=future.result()               #返回的对象类型，是 rclpy 的 ClientGoalHandle代表这次具体导航任务的句柄
           if not goal_handle.accepted:
              self.get_logger().info('Goal rejected')
              self.task_active = False
              self.print_task_summary(False)
              self.finish_skill_action(False,'Nav2 goal rejected',0)
              return 
           
           self.get_logger().info('Goal accepted')
           self._get_result_future=goal_handle.get_result_async()  #goal_handle 本身已经知道它代表的是哪一次导航任务，针对这个具体 Goal，异步请求它最终完成时的结果
           self._get_result_future.add_done_callback(
              self.get_result_callback
           )  
   def get_result_callback(self,future):
       result_response=future.result() #跟上一个future意义不同
       status=result_response.status   #是 ROS2 Action 通用状态，表示任务最后是成功、取消、终止之类
       result=result_response.result 
      #self.get_logger.info(f'status:{status}')  这是 f-string，作用就是把变量的值放进字符串里。
       if status == GoalStatus.STATUS_SUCCEEDED:
   
          if self.retry_count>0:
            self.get_logger().info( f'Navigation succeeded after '
            f'{self.retry_count} retry')
          else:
            self.get_logger().info('Navigation succeeded')
          self.task_active = False
          self.print_task_summary(True)  
          self.finish_skill_action(True,'Navigation Succeeded',0
                                     )
       elif status == GoalStatus.STATUS_CANCELED:
            self.get_logger().info('Navigation canceled')
            self.task_active = False
            self.print_task_summary(False) 
            self.finish_skill_action(
            False,
            'Navigation canceled',
            0
        )

       elif status == GoalStatus.STATUS_ABORTED:
            self.get_logger().error(
            f'Navigation aborted: '
            f'error_code={result.error_code}, '
            f'error_msg={result.error_msg}')
        
            if not self.is_retryable_error(result.error_code):
             self.get_logger().error(
            'Non-retryable planner error, aborting task'
              )
             self.task_active = False
             self.print_task_summary(False)
             message = (
                result.error_msg
                if result.error_msg
                else f'Nav2 error code: {result.error_code}'
            )

             self.finish_skill_action(
                False,
                message,
                result.error_code
            )
             return
   
            self.retry_navigation(result.error_code,
            result.error_msg)

   def retry_navigation(self,error_code,error_msg):                           #重试
              
              if  self.retry_count<self.max_retries:              #允许重试
                  self.retry_count+=1
                  self.get_logger().info(f'Retrying navigate...{self.retry_count}/{self.max_retries}')
                  x,y,yaw=self.current_goal        #属性
                  self.navigate_to_pose(x,y,yaw)
              else:
                  self.get_logger().error('Maximmum retries reached,aborting task')
                  self.task_active=False
                  self.print_task_summary(False)
                  message = (error_msg
                  if error_msg
                  else f'Nav2 error code: {error_code}'
               )

                  self.finish_skill_action(
                    False,
                    message,
                    error_code
               )


   def finish_skill_action(self,success,message,error_code):
       if (
           self._skill_done_future is not None
           and not  self._skill_done_future.done()    #future还没结果_skill_done_future.done()=False
       ):
           self._skill_done_future.set_result(
               (success,message,error_code)
           )
#set rusult把结果放进去;future.result把结果拿出来
  
   def is_retryable_error(self, error_code):
         retryable_errors = [
         ComputePathToPose.Result.TF_ERROR,
         ComputePathToPose.Result.START_OCCUPIED,
         ComputePathToPose.Result.GOAL_OCCUPIED,
         ComputePathToPose.Result.TIMEOUT,
         ComputePathToPose.Result.NO_VALID_PATH 
        ]
         return error_code in retryable_errors 
   

   
   def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback

        self.feedback_count += 1
        self.nav2_recoveries = feedback.number_of_recoveries
        if self.feedback_count%10==0:
         self.get_logger().info(
        f'Distance remaining: {feedback.distance_remaining:.2f} m, '
        f'Nav2 recoveries: {self.nav2_recoveries}'
    )
        if(
            self._skill_goal_handle is not None
                   and self._skill_goal_handle.is_active       ):
             skill_feedback=NavigateSkill.Feedback()   #转换消息类型
             skill_feedback.distance_remaining=(
                 feedback.distance_remaining
             )
             skill_feedback.nav2_recoveries=(
                 feedback.number_of_recoveries
             )
             self._skill_goal_handle.publish_feedback(
                 skill_feedback
             )#通过 Skill ActionServer 发送给 Agent
   def print_task_summary(self,success):
      duration=time.monotonic()-self.task_start_time

      self.get_logger().info(
         f'Task summary: '
         f'success={success}, '
         f'place={self.current_place}, '
         f'duration={duration:.2f}s, '
         f'skill_retries={self.retry_count}, '
         f'nav2_recoveries={self.nav2_recoveries}'
      )   

   async def execute_navigate_skill(self,goal_handle):#ROS2给server的一个对象：当前这个具体 Action 任务的控制句柄
       place=goal_handle.request.place.strip()       #handle实际上是一个形参，rclpy 会按照这个 callback 的接口规定

       self.get_logger().info(
           f'Receive NavigateSkill goal:{place}')
       result=NavigateSkill.Result()        #创建自己定义的Result ROS2 Action Result消息对象

       if place not in self.locations:
          result.success=False
          result.message=f'Unknown location:{place}.'
          result.error_code=0
          goal_handle.abort()
          return result
       if self.task_active:
          result.success=False
          result.message='NavigateSkill is already active.'
          result.error_code=0
          goal_handle.abort()
          return result
        
       self._skill_done_future=Future()      #代表整个 NavigateSkill 任务，创建一个没有结果的Future
       self._skill_goal_handle=goal_handle
       self.navigate(place)
       success,message,error_code=await self._skill_done_future  #await取出了结果,await暂时让出线程，可以去执行另一个回调函数
       self._skill_goal_handle=None
       self._skill_done_future=None
       result.success=success
       result.message=message 
       result.error_code=error_code
       if success :
           goal_handle.succeed()
       else:
           goal_handle.abort()
       return result
#set rusult把结果放进去;future.result把结果拿出来


def main(args=None):
    rclpy.init(args=args) #初始化通信环境

    node= NavigateToPoseSkill()#创建对象并且让对象指向node变量
    #node.navigate('room')
    #node.navigate_to_pose(2.0, 1.0, 0.0)
    rclpy.spin(node)#让node一直运行


    node.destroy_node()#销毁这个节点
    rclpy.shutdown()#关闭ROS2 Python环境

if __name__=='__main__':        #如果是主程序启动就开始执行main()
    main()