'''Business Validator - schema + business rule validation with auto-repair.'''
import json as _json, os as _os, copy as _copy, uuid as _uuid
from dataclasses import dataclass, field
from validators.validator import validate as _schema_validate

@dataclass
class ValidationIssue:
    rule: str; severity: str; path: str; message: str
    auto_fixed: bool = False; fix_applied: str = ""

@dataclass
class ValidationReport:
    report_id: str; valid: bool
    schema_checks: dict = field(default_factory=dict)
    business_checks: list = field(default_factory=list)
    repair_actions: list = field(default_factory=list)
    repaired_data: dict = field(default_factory=dict)
    summary: str = ""
    def to_dict(self):
        return {"report_id":self.report_id,"valid":self.valid,"schema_checks":self.schema_checks,
                "business_checks":[{"rule":i.rule,"severity":i.severity,"path":i.path,"message":i.message,
                "auto_fixed":i.auto_fixed,"fix_applied":i.fix_applied} for i in self.business_checks],
                "repair_actions":self.repair_actions,"summary":self.summary}

class BusinessValidator:
    SCHEMA_MAP = {"structure":"structure.json","workflow":"workflow.json","kpi":"kpi.json","risk":"risk.json"}
    _REPAIR_MAP = {}

    def __init__(self, auto_repair=True):
        self.auto_repair = auto_repair

    def validate(self, compiled):
        report_id = str(_uuid.uuid4())[:12]
        data = _copy.deepcopy(compiled)

        # Phase 1: Schema
        schema_results = {}
        for section, sf in self.SCHEMA_MAP.items():
            if section in data:
                ok, issues, repaired = _schema_validate(data[section], sf)
                schema_results[section] = {"valid":ok,"issues":issues}
                if not ok and self.auto_repair:
                    data[section] = repaired

        # Phase 2: Business rules
        biz = []
        biz += self._ck_struct(data.get("structure",{}))
        biz += self._ck_kpi(data.get("kpi",{}))
        biz += self._ck_wf(data.get("workflow",{}))
        biz += self._ck_risk(data.get("risk",{}), data.get("structure",{}))
        biz += self._ck_cross(data)

        # Phase 3: Repair
        repairs = []
        if self.auto_repair:
            for issue in biz:
                fn = self._REPAIR_MAP.get(issue.rule)
                if fn:
                    try:
                        fn(data, issue)
                        issue.auto_fixed = True
                        issue.fix_applied = "auto-repaired"
                        repairs.append(f"[{issue.rule}] {issue.message} -> repaired")
                    except Exception as e:
                        repairs.append(f"[{issue.rule}] repair failed: {e}")

            # Re-validate after repair
            if repairs:
                biz2 = []
                biz2 += self._ck_struct(data.get("structure",{}))
                biz2 += self._ck_kpi(data.get("kpi",{}))
                biz2 += self._ck_wf(data.get("workflow",{}))
                biz2 += self._ck_risk(data.get("risk",{}), data.get("structure",{}))
                biz2 += self._ck_cross(data)
                biz = biz2

        # Phase 4: Report
        all_schema_ok = all(v["valid"] for v in schema_results.values())
        errors = [i for i in biz if i.severity == "error"]
        warnings = [i for i in biz if i.severity == "warning"]
        is_valid = all_schema_ok and len(errors) == 0

        summary = (
            f"Schema: {sum(1 for v in schema_results.values() if v['valid'])}/{len(schema_results)} sections valid. "
            f"Business: {len(errors)} errors, {len(warnings)} warnings. "
            f"Auto-repairs: {len(repairs)}. "
            f"Overall: {'VALID' if is_valid else 'INVALID'}"
        )
        return ValidationReport(report_id=report_id, valid=is_valid, schema_checks=schema_results,
                                business_checks=errors + warnings, repair_actions=repairs,
                                repaired_data=data, summary=summary)

    # ---- Structure checks ----
    def _ck_struct(self, s):
        issues = []
        a = s.get("actors",[]); wf = s.get("workflow",[]); st = s.get("states",[]); r = s.get("rules",[])
        if not a: issues.append(ValidationIssue("structure.no_actors","error","structure.actors","No actors defined"))
        if not wf: issues.append(ValidationIssue("structure.no_workflow","error","structure.workflow","No workflow steps"))
        if not st: issues.append(ValidationIssue("structure.no_states","error","structure.states","No states defined"))
        if st and not any(x.get("is_initial") for x in st):
            issues.append(ValidationIssue("structure.no_initial_state","error","structure.states","No initial state"))
        if st and not any(x.get("is_terminal") for x in st):
            issues.append(ValidationIssue("structure.no_terminal_state","warning","structure.states","No terminal state"))
        if len(r) < 2:
            issues.append(ValidationIssue("structure.few_rules","warning","structure.rules",f"Only {len(r)} rule(s). Recommend >= 3."))
        return issues

    # ---- KPI checks ----
    def _ck_kpi(self, kpi):
        issues = []
        metrics = kpi.get("metrics",[])
        if not metrics:
            issues.append(ValidationIssue("kpi.metrics_empty","error","kpi.metrics","KPI metrics array is empty"))
            return issues
        if len(metrics) < 4:
            issues.append(ValidationIssue("kpi.too_few_metrics","warning","kpi.metrics",f"Only {len(metrics)} metrics. Recommend >= 8."))
        for m in metrics:
            mid = m.get("id","?")
            if not m.get("formula","").strip():
                issues.append(ValidationIssue("kpi.missing_formula","error",f"kpi.metrics.{mid}",f"Metric '{m.get('name',mid)}' has no formula"))
            if not m.get("target",""):
                issues.append(ValidationIssue("kpi.missing_target","warning",f"kpi.metrics.{mid}",f"Metric '{m.get('name',mid)}' has no target"))
        tree = kpi.get("tree",{})
        branches = tree.get("branches",[])
        if branches:
            total = sum(b.get("weight",0) for b in branches)
            if abs(total - 1.0) > 0.02:
                issues.append(ValidationIssue("kpi.weights_not_sum_to_1","warning","kpi.tree",f"Weights sum to {total:.2f}"))
        if not kpi.get("alerts",[]):
            issues.append(ValidationIssue("kpi.no_alerts","warning","kpi.alerts","No alert rules configured"))
        return issues

    # ---- Workflow checks ----
    def _ck_wf(self, wf):
        issues = []
        nodes = wf.get("nodes",[])
        edges = wf.get("edges",[])
        if not nodes: return issues
        nids = {n["id"] for n in nodes}
        starts = [n["id"] for n in nodes if n.get("type")=="start"]
        ends = [n["id"] for n in nodes if n.get("type")=="end"]
        if not starts: issues.append(ValidationIssue("workflow.no_start","error","workflow.nodes","No start node"))
        if not ends: issues.append(ValidationIssue("workflow.no_end","error","workflow.nodes","No end node"))
        adj = {}; rev = {}
        for e in edges:
            f,t = e.get("from"), e.get("to")
            if f in nids and t in nids:
                adj.setdefault(f,[]).append(t); rev.setdefault(t,[]).append(f)
        # BFS from starts
        reachable = set()
        for sn in starts:
            q = [sn]
            while q:
                cur = q.pop(0)
                if cur not in reachable:
                    reachable.add(cur)
                    for nx in adj.get(cur,[]):
                        if nx not in reachable: q.append(nx)
        unreach = nids - reachable
        if unreach: issues.append(ValidationIssue("workflow.unreachable_nodes","error","workflow.nodes",f"Unreachable: {unreach}"))
        # Reverse BFS from ends
        can_end = set()
        for en in ends:
            q = [en]
            while q:
                cur = q.pop(0)
                if cur not in can_end:
                    can_end.add(cur)
                    for pr in rev.get(cur,[]):
                        if pr not in can_end: q.append(pr)
        dead = nids - can_end
        if dead: issues.append(ValidationIssue("workflow.dead_ends","warning","workflow.nodes",f"Cannot reach end: {dead}"))
        # Orphan edges
        for e in edges:
            if e.get("from") not in nids:
                issues.append(ValidationIssue("workflow.orphan_edge","error",f"workflow.edges",f"Edge from '{e.get('from')}' -> unknown node"))
            if e.get("to") not in nids:
                issues.append(ValidationIssue("workflow.orphan_edge","error",f"workflow.edges",f"Edge to '{e.get('to')}' -> unknown node"))
        return issues

    # ---- Risk checks ----
    def _ck_risk(self, risk, structure):
        issues = []
        rm = risk.get("risk_matrix",[])
        if not rm: issues.append(ValidationIssue("risk.empty_matrix","error","risk.risk_matrix","Risk matrix is empty"))
        if len(rm) < 3: issues.append(ValidationIssue("risk.too_few_risks","warning","risk.risk_matrix",f"Only {len(rm)} risks"))
        pm = {"low":1,"medium":2,"high":3}
        for r in rm:
            exp = pm.get(r.get("probability","").lower(),1) * pm.get(r.get("impact","").lower(),1)
            if r.get("score",0) != exp:
                issues.append(ValidationIssue("risk.score_mismatch","warning",f"risk.risk_matrix.{r.get('id','?')}",f"Score {r.get('score')} != {exp}"))
        rids = {r.get("id") for r in rm}
        for m in risk.get("mitigations",[]):
            if m.get("risk_id") not in rids:
                issues.append(ValidationIssue("risk.orphan_mitigation","warning",f"risk.mitigations",f"Unknown risk_id '{m.get('risk_id')}'"))
        # Check bottleneck labels against workflow node labels
        wf_nodes = structure.get("workflow",[])
        wf_labels = {n.get("label","") for n in wf_nodes} if isinstance(wf_nodes,list) else set()
        for b in risk.get("bottlenecks",[]):
            bn = b.get("node","")
            if wf_labels and bn not in wf_labels:
                issues.append(ValidationIssue("risk.bottleneck_unknown_node","warning","risk.bottlenecks",f"'{bn}' not in workflow nodes"))
        if not risk.get("optimizations",[]):
            issues.append(ValidationIssue("risk.no_optimizations","warning","risk.optimizations","No optimizations"))
        return issues

    # ---- Cross-section ----
    def _ck_cross(self, data):
        issues = []
        s = data.get("structure",{})
        wf = data.get("workflow",{})
        if len(s.get("actors",[])) != len(wf.get("swimlanes",[])):
            issues.append(ValidationIssue("cross.actor_swimlane_mismatch","warning","cross","Actor/swimlane count mismatch"))
        kpi = data.get("kpi",{})
        br = kpi.get("tree",{}).get("branches",[])
        if br and len(br) != 5:
            issues.append(ValidationIssue("cross.kpi_branch_count","warning","kpi.tree",f"Expected 5 branches, got {len(br)}"))
        return issues

# ---- Repair functions ----
def _reg(rule):
    def d(fn): BusinessValidator._REPAIR_MAP[rule]=fn; return fn
    return d

@_reg("structure.no_initial_state")
def _(d,i): d.get("structure",{}).get("states",[])[0]["is_initial"]=True if d.get("structure",{}).get("states",[]) else None

@_reg("structure.no_terminal_state")
def _(d,i):
    st=d.get("structure",{}).get("states",[]); st[-1]["is_terminal"]=True if st else None

@_reg("structure.no_actors")
def _(d,i): d.setdefault("structure",{})["actors"]=[{"id":"a1","role":"User","responsibilities":["Submit"],"inputs":["Data"],"outputs":["Result"]}]

@_reg("structure.no_workflow")
def _(d,i): d.setdefault("structure",{})["workflow"]=[{"step":1,"actor":"User","action":"Submit","condition":"","input":"Data","output":"Result","next":"end","sla_hours":24}]

@_reg("structure.no_states")
def _(d,i): d.setdefault("structure",{})["states"]=[{"name":"idle","is_initial":True,"is_terminal":False,"transitions":[{"to":"done","trigger":"process","guard":""}]},{"name":"done","is_initial":False,"is_terminal":True,"transitions":[]}]

@_reg("kpi.metrics_empty")
def _(d,i):
    d.setdefault("kpi",{})["metrics"]=[
        {"id":"M1","name":"Throughput","formula":"items/day","target":">100","branch":"Efficiency","direction":"higher_better"},
        {"id":"M2","name":"Error Rate","formula":"errors/total","target":"<1%","branch":"Quality","direction":"lower_better"},
        {"id":"M3","name":"Queue Length","formula":"pending_count","target":"<50","branch":"Capacity","direction":"lower_better"},
        {"id":"M4","name":"Cost Per Item","formula":"cost/items","target":"<5","branch":"Cost","direction":"lower_better"}
    ]

@_reg("kpi.missing_formula")
def _(d,i):
    for m in d.get("kpi",{}).get("metrics",[]):
        if not m.get("formula"): m["formula"]="TBD"

@_reg("kpi.weights_not_sum_to_1")
def _(d,i):
    br=d.get("kpi",{}).get("tree",{}).get("branches",[])
    if br:
        n=len(br)
        for b in br: b["weight"]=round(1.0/n,4)

@_reg("workflow.no_start")
def _(d,i):
    ns=d.get("workflow",{}).get("nodes",[])
    if ns: ns[0]["type"]="start"

@_reg("workflow.no_end")
def _(d,i):
    ns=d.get("workflow",{}).get("nodes",[])
    if ns:
        ns[-1]["type"]="end"
        lid=ns[-1]["id"]
        d["workflow"]["edges"]=[e for e in d.get("workflow",{}).get("edges",[]) if e.get("from")!=lid]

@_reg("workflow.unreachable_nodes")
def _(d,i):
    ns=d.get("workflow",{}).get("nodes",[]); es=d.get("workflow",{}).get("edges",[])
    nids={n["id"] for n in ns}; starts=[n["id"] for n in ns if n.get("type")=="start"]
    adj={}
    for e in es: adj.setdefault(e["from"],[]).append(e["to"])
    reachable=set()
    for sn in starts:
        q=[sn]
        while q:
            cur=q.pop(0)
            if cur not in reachable:
                reachable.add(cur)
                for nx in adj.get(cur,[]): q.append(nx)
    unreach=nids-reachable
    if unreach and reachable:
        bridge=list(reachable)[-1]
        for uid in unreach: es.append({"from":bridge,"to":uid,"label":"repaired"})

@_reg("workflow.dead_ends")
def _(d,i):
    ns=d.get("workflow",{}).get("nodes",[]); es=d.get("workflow",{}).get("edges",[])
    ends=[n["id"] for n in ns if n.get("type")=="end"]
    if not ends: return
    has_out={e["from"] for e in es}
    dead={n["id"] for n in ns if n["id"] not in has_out and n.get("type")!="end"}
    for de in dead: es.append({"from":de,"to":ends[0],"label":"repaired"})

@_reg("workflow.orphan_edge")
def _(d,i):
    nids={n["id"] for n in d.get("workflow",{}).get("nodes",[])}
    d["workflow"]["edges"]=[e for e in d.get("workflow",{}).get("edges",[]) if e.get("from") in nids and e.get("to") in nids]

@_reg("risk.empty_matrix")
def _(d,i):
    d.setdefault("risk",{})["risk_matrix"]=[
        {"id":"R1","risk":"Operational failure","category":"operational","probability":"low","impact":"high","score":3,"trigger":"Error","owner":"Ops"},
        {"id":"R2","risk":"Quality degradation","category":"quality","probability":"medium","impact":"medium","score":4,"trigger":"Bug","owner":"QA"},
        {"id":"R3","risk":"Capacity overload","category":"capacity","probability":"medium","impact":"high","score":6,"trigger":"Spike","owner":"Ops"}
    ]

@_reg("risk.score_mismatch")
def _(d,i):
    pm={"low":1,"medium":2,"high":3}
    for r in d.get("risk",{}).get("risk_matrix",[]):
        r["score"]=pm.get(r.get("probability","").lower(),1)*pm.get(r.get("impact","").lower(),1)
