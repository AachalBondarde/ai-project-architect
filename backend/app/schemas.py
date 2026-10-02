from pydantic import BaseModel
from typing import List
class Req(BaseModel): summary:str; functional:List[str]; non_functional:List[str]; constraints:List[str]; missing_info:List[str]; questions:List[str]
class Alt(BaseModel): name:str; why:str
class Arch(BaseModel): recommended:str; rationale:str; components:List[str]; tradeoffs:List[str]; alternatives:List[Alt]
class Tech(BaseModel): layer:str; name:str; purpose:str; why_fits:str; alternatives:List[str]
class TechStack(BaseModel): items:List[Tech]
class Entity(BaseModel): name:str; attributes:List[str]; relationships:List[str]; indexes:List[str]
class Db(BaseModel): type:str; rationale:str; entities:List[Entity]
class Endpoint(BaseModel): method:str; path:str; summary:str; auth:bool
class Api(BaseModel): endpoints:List[Endpoint]
class Diagrams(BaseModel): system:str; component:str; dataflow:str
class Security(BaseModel): checklist:List[str]; threats:List[str]; auth:str; secrets:str; encryption:str
class Issue(BaseModel): severity:str; title:str; suggestion:str
class Review(BaseModel): score:int; approved:bool; issues:List[Issue]
class Phase(BaseModel): name:str; tasks:List[str]; effort:str; priority:str
class Roadmap(BaseModel): phases:List[Phase]
