from robot_agent.agent.action_validator import validate_action

class ToolRegistry:

    def __init__(self): #创建类时自动执行
        self._handlers={}
        #负责注册工具
    def register(self,name:str,handler):
        if not callable(handler):      #callable() 是 Python 内置函数，用于判断一个对象能否被调用。
            raise TypeError("handler 必须是可调用对象")

        if name in self._handlers:
            raise ValueError(f"Tool already registered:{name}")

        self._handlers[name]=handler

    def execute(self,name:str,arguments:dict):
        #先验证，不能直接执行未验证的参数
        validated=validate_action(name,arguments)

        #检查是否注册了对应的处理函数
        if name not in self._handlers:
            raise ValueError(f"Tool not registered:{name}")
        #找到函数并调用，将验证后的对象传进去
        handler=self._handlers[name]

        return handler(validated)    #返回调用的函数结果