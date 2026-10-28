from typing import Literal    #Literal 是 Python typing 模块提供的类型标注工具
from pathlib import Path
import yaml
from typing import  Literal
from pydantic import BaseModel,ConfigDict,field_validator

#打开 YAML 文件，读取允许导航的地点，并返回一个 Python 列表。
def load_locations():
    path=(
        Path(__file__).resolve().parent.parent
        /"config"
        /"locations.yaml"
    )
    with path.open("r",encoding="utf-8") as f:
        config=yaml.safe_load(f)      #读取文件对象 f 中的 YAML 内容，把它转换成 Python 数据，然后保存到变量 config 中。
    loactions=config["locations"]

    if not isinstance(loactions,list): #isinstance() 是 Python 的内置函数，用于判断一个对象是否属于指定类型
        raise ValueError("locations 必须是列表")
    return loactions


#BaseModel 会读取我们声明的字段及其类型信息，并利用 Pydantic 的验证机制检查实际传入的数据
class NavigateArguments(BaseModel):
    model_config=ConfigDict(extra='forbid')
    target:str

    @field_validator("target")       #Pydantic 提供的字段验证器装饰器;当 Pydantic 验证 target 字段时，还要运行我们自己写的 check_target() 函数
    @classmethod                     #@classmethod 表示这是一个类方法。
    def check_target(cls,value:str) -> str:   #cls代表类本身
        locations=load_locations()
        if value not in locations:
            raise ValueError(f"Unkonwn location:{value}")
        return value 

   # target:Literal["kitchen","room"]  #表示这个字段允许的值限定为 "kitchen" 或 "room"，类型标注


def validate_action(name:str,arguments:dict):    #类型标注
    if name !="navigate_to_location":
        raise ValueError(f"Unkonwn tool:{name}")
    #返回值是一个实力对象，通过属性进行进行访问，如果验证没通过会抛出异常
    result=NavigateArguments.model_validate(arguments) #Model_vaildate会检查传入数据是否符合 NavigateArguments 的定义
    return result
