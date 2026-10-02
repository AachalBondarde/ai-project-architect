import os, json, time
from . import schemas as S
from .rag import retrieve
def _llm():
    if not os.getenv("OPENAI_API_KEY"): return None
    try:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=os.getenv("LLM_MODEL", "gpt-4o-mini"),temperature=0.2)
    except Exception: return None
class BaseAgent:
    name=""; schema=None; instruction=""
    def run(self,st):
        t=time.time(); ctx="\n".join(retrieve(st["idea"]+" "+self.name))
        llm=_llm(); out=None
        if llm:
            try:
                from langchain_core.prompts import ChatPromptTemplate
                p=ChatPromptTemplate.from_messages([("system","You are the {name} of a software architecture team. {ins}\nKnowledge:\n{ctx}"),("human","Project: {idea}\nPrior outputs: {prior}")])
                out=(p|llm.with_structured_output(self.schema)).invoke({"name":self.name,"ins":self.instruction,"ctx":ctx,"idea":st["idea"],"prior":json.dumps(st["out"])[:6000]}).model_dump()
            except Exception: out=None
        if out is None: out=self.heuristic(st).model_dump()
        st["out"][self.name]=out; st["log"].append({"agent":self.name,"seconds":round(time.time()-t,2),"rag":ctx[:120]})
        return out
def _big(st): return st["users"]>=20000
class Requirements(BaseAgent):
    name="requirements"; schema=S.Req; instruction="Extract requirements."
    def heuristic(self,st):
        return S.Req(summary=st["idea"][:300],functional=["User registration and login","Core CRUD for main entities","Search and filtering","Notifications","Admin dashboard"],
          non_functional=[f"Support ~{st['users']} users","API p95 < 300ms","99.5% availability"],constraints=[f"Budget: {st['budget']}",f"Timeline: {st['timeline']}"],
          missing_info=["Payment needs","Third-party integrations"],questions=["Is mobile support required?","Any compliance rules (GDPR/FERPA)?"])
class Architecture(BaseAgent):
    name="architecture"; schema=S.Arch; instruction="Recommend architecture with alternatives."
    def heuristic(self,st):
        r="Microservices with API gateway" if _big(st) else "Modular monolith"
        return S.Arch(recommended=r,rationale=f"Fits {st['users']} users and a small team; lower ops cost.",components=["Web client","API layer","Auth module","Domain modules","Database","Cache","Notification worker"],
          tradeoffs=["Simplicity vs independent scaling","Single deploy vs team autonomy"],alternatives=[S.Alt(name="Microservices",why="Independent scaling, higher complexity"),S.Alt(name="Serverless",why="Pay-per-use, cold starts")])
class TechStackAgent(BaseAgent):
    name="tech_stack"; schema=S.TechStack; instruction="Select tech stack."
    def heuristic(self,st):
        T=lambda l,n,p,w,a:S.Tech(layer=l,name=n,purpose=p,why_fits=w,alternatives=a)
        return S.TechStack(items=[T("Frontend","React + Vite","UI","Fast DX, large ecosystem",["Vue","Angular"]),T("Backend","FastAPI","REST API","Async, OpenAPI, Pydantic",["Django","Express"]),
          T("Database","PostgreSQL","Relational store","Transactions and relations",["MySQL","MongoDB"]),T("Cache","Redis","Sessions/cache","Low-latency reads",["Memcached"]),
          T("Auth","JWT + RBAC","Access control","Stateless, simple",["OAuth provider"]),T("Deployment","Docker + CI/CD","Packaging","Reproducible",["Kubernetes"])])
class Database(BaseAgent):
    name="database"; schema=S.Db; instruction="Design database."
    def heuristic(self,st):
        E=lambda n,a,r,i:S.Entity(name=n,attributes=a,relationships=r,indexes=i)
        return S.Db(type="SQL (PostgreSQL)",rationale="Relational integrity for users, items and bookings.",entities=[
          E("User",["id PK","name","email UNIQUE","password_hash","role"],["1:N Item"],["email"]),
          E("Item",["id PK","title","description","owner_id FK","created_at"],["N:1 User","1:N Registration"],["owner_id","created_at"]),
          E("Registration",["id PK","user_id FK","item_id FK","status"],["N:1 User","N:1 Item"],["user_id,item_id UNIQUE"])])
class Api(BaseAgent):
    name="api"; schema=S.Api; instruction="Design REST API."
    def heuristic(self,st):
        e=lambda m,p,s,a=True:S.Endpoint(method=m,path=p,summary=s,auth=a)
        return S.Api(endpoints=[e("POST","/api/auth/register","Register",False),e("POST","/api/auth/login","Login",False),e("GET","/api/items","List items",False),e("POST","/api/items","Create item"),
          e("GET","/api/items/{id}","Item detail",False),e("PUT","/api/items/{id}","Update item"),e("DELETE","/api/items/{id}","Delete item"),e("POST","/api/items/{id}/register","Register for item")])
class Diagram(BaseAgent):
    name="diagrams"; schema=S.Diagrams; instruction="Create Mermaid diagrams."
    def heuristic(self,st):
        a=st["out"]["architecture"]["recommended"]
        return S.Diagrams(system=f"graph TD\n U[User]-->W[React Client]\n W-->G[API: {a}]\n G-->D[(PostgreSQL)]\n G-->C[(Redis)]\n G-->Q[Worker]",
          component="graph LR\n Auth-->API\n API-->Items\n API-->Notifications\n Items-->DB[(DB)]",
          dataflow="sequenceDiagram\n User->>Client: Action\n Client->>API: HTTPS + JWT\n API->>DB: Query\n DB-->>API: Rows\n API-->>Client: JSON")
class SecurityAgent(BaseAgent):
    name="security"; schema=S.Security; instruction="Audit security (OWASP)."
    def heuristic(self,st):
        return S.Security(checklist=["Password hashing (bcrypt)","Input validation (Pydantic)","HTTPS everywhere","CORS allowlist"],threats=["Injection","Broken access control","Credential stuffing"],
          auth="JWT access tokens, 15 min expiry, role-based access",secrets="Environment variables / secret manager",encryption="TLS in transit, encrypted DB volumes at rest")
class Reviewer(BaseAgent):
    name="reviewer"; schema=S.Review; instruction="Audit consistency across all outputs; list issues by severity."
    def heuristic(self,st):
        o=st["out"]; iss=[]
        if not any("rate limit" in c.lower() for c in o["security"]["checklist"]): iss.append(S.Issue(severity="High",title="No rate limiting",suggestion="Add rate limiting on auth endpoints"))
        if not any("refresh" in o["security"]["auth"].lower() for _ in [0]): iss.append(S.Issue(severity="Medium",title="No refresh-token strategy",suggestion="Add refresh tokens with rotation"))
        if _big(st) and "monolith" in o["architecture"]["recommended"].lower(): iss.append(S.Issue(severity="High",title="Architecture/scale mismatch",suggestion="Use services"))
        return S.Review(score=max(50,100-15*len(iss)),approved=not iss,issues=iss)
class Roadmap(BaseAgent):
    name="roadmap"; schema=S.Roadmap; instruction="Create 6-phase roadmap."
    def heuristic(self,st):
        P=lambda n,t,e,p:S.Phase(name=n,tasks=t,effort=e,priority=p)
        return S.Roadmap(phases=[P("1 Planning",["Finalize requirements","Wireframes"],"1 wk","High"),P("2 Core Development",["Auth","CRUD APIs","UI"],"4 wk","High"),P("3 Integration",["Notifications","Payments/3rd party"],"2 wk","Medium"),
          P("4 Testing",["Unit/E2E tests","Security scan"],"2 wk","High"),P("5 Deployment",["CI/CD","Monitoring"],"1 wk","High"),P("6 Future Enhancements",["Analytics","Mobile app"],"Ongoing","Low")])
PIPELINE=[Requirements(),Architecture(),TechStackAgent(),Database(),Api(),Diagram(),SecurityAgent()]
def revise(st):
    """Revision engine: applies reviewer suggestions deterministically (and notes them)."""
    o=st["out"]
    for i in o["reviewer"]["issues"]:
        t=i["title"]
        if "rate" in t.lower(): o["security"]["checklist"].append("Rate limiting on auth and public endpoints")
        elif "refresh" in t.lower(): o["security"]["auth"]+="; refresh tokens with rotation"
        elif "mismatch" in t.lower(): o["architecture"]["recommended"]="Microservices with API gateway"
