from .agents import PIPELINE, Reviewer, Roadmap, revise
def run_pipeline(idea,users=5000,budget="Low",timeline="3 months"):
    """Generator yielding SSE-style events; final event carries the blueprint."""
    st={"idea":idea,"users":users,"budget":budget,"timeline":timeline,"out":{},"log":[],"review_iterations":0,"history":[]}
    for a in PIPELINE:
        yield {"event":"start","agent":a.name}; a.run(st); yield {"event":"done","agent":a.name}
    rv=Reviewer()
    for it in range(3):  # initial review + max 2 revision loops
        yield {"event":"start","agent":"reviewer"}; r=rv.run(st); st["history"].append(r); yield {"event":"done","agent":"reviewer","approved":r["approved"],"issues":len(r["issues"])}
        if r["approved"] or it==2: break
        st["review_iterations"]+=1; yield {"event":"start","agent":"revision"}; revise(st); yield {"event":"done","agent":"revision"}
    yield {"event":"start","agent":"roadmap"}; Roadmap().run(st); yield {"event":"done","agent":"roadmap"}
    yield {"event":"complete","blueprint":{**st["out"],"review_history":st["history"],"logs":st["log"],"idea":idea}}
