var et=Object.defineProperty;var Be=Object.getOwnPropertySymbols;var tt=Object.prototype.hasOwnProperty,st=Object.prototype.propertyIsEnumerable;var Ee=(y,p,m)=>p in y?et(y,p,{enumerable:!0,configurable:!0,writable:!0,value:m}):y[p]=m,Ne=(y,p)=>{for(var m in p||(p={}))tt.call(p,m)&&Ee(y,m,p[m]);if(Be)for(var m of Be(p))st.call(p,m)&&Ee(y,m,p[m]);return y};var J=(y,p,m)=>new Promise((F,C)=>{var V=O=>{try{K(m.next(O))}catch(U){C(U)}},W=O=>{try{K(m.throw(O))}catch(U){C(U)}},K=O=>O.done?F(O.value):Promise.resolve(O.value).then(V,W);K((m=m.apply(y,p)).next())});import{b as be,G as Ae,au as at,o as l,k as $,H as q,T as ot,I as le,e as r,f as e,z as Le,n as ee,g as Se,h as E,i as s,l as w,p as g,X as Ie,j as z,av as lt,c as Z,r as T,_ as $e,aw as nt,ax as it,J as te,K as se,ay as dt,az as rt,v as Je,u as ct,w as We,aA as ut,a8 as He,aB as mt,a6 as Ke,aC as fe,aa as Xe,ag as ye,aD as Oe,aE as pt,A as B,aF as Fe,B as Q,V as _e,ab as vt,aG as gt,aH as _t,ah as ht,ak as Re,aI as ft,aJ as yt,ac as Ye,aK as bt,aL as $t,aM as Ge,aN as je,a9 as kt,aO as wt,aP as Ct}from"./index-B-Xi4Pic.js";import{i as Qe,j as Te,k as Mt,l as Ve,M as zt,S as pe,m as St,n as Tt,o as Vt,b as Ze}from"./agentTeams-CjtEwgAw.js";import{M as Dt,L as Ut}from"./useKeyboard-CY_rtg5V.js";import{u as At}from"./useModelCatalog-nF7nEoge.js";import{r as Lt,a as Pt,f as Bt,b as Et}from"./providerRuntime-Bim9Xk0P.js";import"./countbot-logo-CNglRKg-.js";const Nt=["aria-labelledby"],Ht={key:0,class:"drawer-header"},Ot=["id"],Ft=["aria-label"],Rt={class:"drawer-body"},Gt={key:1,class:"drawer-footer"},jt=be({__name:"Drawer",props:{modelValue:{type:Boolean},title:{default:""},size:{default:"medium"},placement:{default:"right"},closable:{type:Boolean,default:!0},maskClosable:{type:Boolean,default:!1},showHeader:{type:Boolean,default:!0}},emits:["update:modelValue","close"],setup(y,{emit:p}){const m=y,F=p,C=Z(()=>`drawer-title-${Math.random().toString(36).slice(2,9)}`),V=T(),W=()=>{F("update:modelValue",!1),F("close")},K=()=>{m.maskClosable&&W()},O=U=>{U.key==="Escape"&&m.modelValue&&m.closable&&W()};return Ae(()=>m.modelValue,U=>{document.body.style.overflow=U?"hidden":"",U?(document.addEventListener("keydown",O),setTimeout(()=>{var k;const N=(k=V.value)==null?void 0:k.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');N==null||N.focus()},60)):document.removeEventListener("keydown",O)},{immediate:!0}),at(()=>{document.removeEventListener("keydown",O),document.body.style.overflow=""}),(U,N)=>(l(),$(lt,{to:"body"},[q(ot,{name:"drawer"},{default:le(()=>[y.modelValue?(l(),r("div",{key:0,class:"drawer-overlay",onClick:K},[e("aside",{ref_key:"panelRef",ref:V,class:ee(["drawer-panel",[`drawer-${y.size}`,`drawer-${y.placement}`]]),role:"dialog","aria-modal":"true","aria-labelledby":C.value,onClick:N[0]||(N[0]=Le(()=>{},["stop"]))},[y.showHeader?(l(),r("header",Ht,[e("h2",{id:C.value,class:"drawer-title"},[Se(U.$slots,"title",{},()=>[E(s(y.title),1)],!0)],8,Ot),y.closable?(l(),r("button",{key:0,type:"button",class:"drawer-close","aria-label":U.$t("common.close"),onClick:W},[(l(),$(w(g(Ie)),{size:18}))],8,Ft)):z("",!0)])):z("",!0),e("div",Rt,[Se(U.$slots,"default",{},void 0,!0)]),U.$slots.footer?(l(),r("footer",Gt,[Se(U.$slots,"footer",{},void 0,!0)])):z("",!0)],10,Nt)])):z("",!0)]),_:3})]))}}),qt=$e(jt,[["__scopeId","data-v-b1db600d"]]),It={class:"dependency-graph"},Jt={class:"graph-header"},Wt={class:"graph-controls"},Kt=["title"],Xt=["title"],Yt={id:"arrowhead",markerWidth:"10",markerHeight:"10",refX:"9",refY:"3",orient:"auto"},Qt=["fill"],Zt={class:"edges"},xt=["x1","y1","x2","y2","marker-end"],es={class:"nodes"},ts=["transform","onClick","onMouseenter"],ss=["x","y"],as={class:"node-label","text-anchor":"middle",dy:"0.3em"},os=["y"],ls={class:"tooltip-content"},ns={key:0},is={key:1,class:"tooltip-deps"},ds={class:"tooltip-label"},rs={key:0,class:"cycle-warning"},De=140,me=60,Ue=200,cs=120,us=be({__name:"DependencyGraph",props:{agents:{}},setup(y){const p=y,m=T(),F=T(),C=T(null),V=T(null),W=Z(()=>typeof window!="undefined"&&m.value&&getComputedStyle(m.value).getPropertyValue("--text-tertiary").trim()||"var(--text-tertiary)"),K=()=>{const v=new Map,_=new Set,D=h=>{if(_.has(h))return v.get(h)||0;_.add(h);const d=p.agents.find(P=>P.id===h);if(!d||!d.depends_on||d.depends_on.length===0)return v.set(h,0),0;const j=Math.max(...d.depends_on.map(P=>D(P)))+1;return v.set(h,j),j};return p.agents.forEach(h=>D(h.id)),v},O=()=>{const v=[],_=new Set,D=new Set,h=[],d=L=>{_.add(L),D.add(L),h.push(L);const j=p.agents.find(P=>P.id===L);if(j!=null&&j.depends_on){for(const P of j.depends_on)if(_.has(P)){if(D.has(P)){const b=h.indexOf(P);return v.push(h.slice(b)),!0}}else if(d(P))return!0}return h.pop(),D.delete(L),!1};return p.agents.forEach(L=>{_.has(L.id)||d(L.id)}),v},U=Z(()=>O()),N=Z(()=>{const v=K(),_=new Map,D=p.agents.map(d=>({id:d.id,label:d.role||d.id,task:d.task,depends_on:d.depends_on||[],hasCondition:!!d.condition,x:0,y:0,level:v.get(d.id)||0}));D.forEach(d=>{const L=d.level;_.has(L)||_.set(L,[]),_.get(L).push(d)});const h=800;return _.forEach((d,L)=>{const j=d.length*Ue,P=(h-j)/2+Ue/2,b=80+L*cs;d.forEach((u,ne)=>{u.x=P+ne*Ue,u.y=b})}),D}),k=Z(()=>{const v=[];return N.value.forEach(_=>{_.depends_on.forEach(D=>{const h=N.value.find(d=>d.id===D);h&&v.push({from:D,to:_.id,x1:h.x,y1:h.y+me/2,x2:_.x,y2:_.y-me/2})})}),v}),oe=v=>{C.value=C.value===v?null:v},X=v=>{if(!C.value)return!1;const _=N.value.find(D=>D.id===C.value);return _?v.from===C.value||v.to===C.value||_.depends_on.includes(v.from)||N.value.some(D=>D.depends_on.includes(C.value)&&D.id===v.to):!1},H=v=>N.value.find(_=>_.id===v),A=v=>{const _=H(v);return _?{left:`${_.x+De/2+10}px`,top:`${_.y-me/2}px`}:{}},I=()=>{C.value=null},ae=()=>{C.value=null};return(v,_)=>{var D,h,d,L,j,P;return l(),r("div",It,[e("div",Jt,[e("h3",null,s(v.$t("teams.dependency.title")),1),e("div",Wt,[e("button",{class:"control-btn",onClick:I,title:v.$t("teams.dependency.resetView")},[(l(),$(w(g(nt)),{size:16}))],8,Kt),e("button",{class:"control-btn",onClick:ae,title:v.$t("teams.dependency.autoLayout")},[(l(),$(w(g(it)),{size:16}))],8,Xt)])]),e("div",{ref_key:"graphContainer",ref:m,class:"graph-container"},[(l(),r("svg",{ref_key:"svgElement",ref:F,class:"graph-svg"},[e("defs",null,[e("marker",Yt,[e("polygon",{points:"0 0, 10 3, 0 6",fill:W.value},null,8,Qt)]),_[1]||(_[1]=e("marker",{id:"arrowhead-highlighted",markerWidth:"10",markerHeight:"10",refX:"9",refY:"3",orient:"auto"},[e("polygon",{points:"0 0, 10 3, 0 6",fill:"var(--color-accent)"})],-1))]),e("g",Zt,[(l(!0),r(te,null,se(k.value,b=>(l(),r("line",{key:`${b.from}-${b.to}`,x1:b.x1,y1:b.y1,x2:b.x2,y2:b.y2,class:ee(["edge",{highlighted:X(b)}]),"marker-end":X(b)?"url(#arrowhead-highlighted)":"url(#arrowhead)"},null,10,xt))),128))]),e("g",es,[(l(!0),r(te,null,se(N.value,b=>(l(),r("g",{key:b.id,transform:`translate(${b.x}, ${b.y})`,class:ee(["node",{highlighted:C.value===b.id,"has-condition":b.hasCondition}]),onClick:u=>oe(b.id),onMouseenter:u=>V.value=b.id,onMouseleave:_[0]||(_[0]=u=>V.value=null)},[e("rect",{width:De,height:me,x:-De/2,y:-me/2,rx:"8",class:"node-rect"},null,8,ss),e("text",as,s(b.label),1),b.hasCondition?(l(),r("text",{key:0,class:"condition-indicator","text-anchor":"middle",y:me/2-8,"font-size":"10"},s(v.$t("teams.dependency.conditional")),9,os)):z("",!0)],42,ts))),128))])],512)),V.value?(l(),r("div",{key:0,class:"node-tooltip",style:dt(A(V.value))},[e("div",ls,[e("strong",null,s((D=H(V.value))==null?void 0:D.label),1),(h=H(V.value))!=null&&h.task?(l(),r("p",ns,s((d=H(V.value))==null?void 0:d.task),1)):z("",!0),(j=(L=H(V.value))==null?void 0:L.depends_on)!=null&&j.length?(l(),r("div",is,[e("span",ds,s(v.$t("teams.dependency.depends")),1),E(" "+s((P=H(V.value))==null?void 0:P.depends_on.join(", ")),1)])):z("",!0)])],4)):z("",!0)],512),U.value.length>0?(l(),r("div",rs,[(l(),$(w(g(rt)),{size:16})),e("div",null,[e("strong",null,s(v.$t("teams.dependency.cycleDetected")),1),(l(!0),r(te,null,se(U.value,(b,u)=>(l(),r("p",{key:u},s(b.join(" → "))+" → "+s(b[0]),1))),128))])])):z("",!0)])}}}),ms=$e(us,[["__scopeId","data-v-38c6926c"]]),ps={class:"team-detail"},vs={class:"detail-header"},gs={class:"team-info-section"},_s={class:"team-title-row"},hs={class:"team-badges"},fs={class:"badge badge-mode"},ys={key:0,class:"team-description"},bs={class:"members-section"},$s={class:"section-header"},ks={class:"section-actions"},ws={key:0,class:"graph-section"},Cs={key:1,class:"empty-members"},Ms={key:2,class:"members-list"},zs={class:"member-header"},Ss={class:"member-info"},Ts={class:"member-number"},Vs={class:"member-actions"},Ds=["onClick"],Us=["onClick"],As={class:"member-details"},Ls={class:"detail-item"},Ps={class:"detail-value"},Bs={key:0,class:"detail-item"},Es={class:"detail-label"},Ns={class:"detail-value"},Hs={key:1,class:"detail-item"},Os={class:"detail-label"},Fs={class:"detail-value"},Rs={key:2,class:"detail-item"},Gs={class:"detail-label"},js={class:"detail-value"},qs={key:3,class:"detail-item full-width"},Is={class:"detail-label"},Js={class:"condition-badge"},Ws={class:"condition-type"},Ks={class:"condition-node"},Xs={class:"condition-text"},Ys={key:4,class:"detail-item full-width"},Qs={class:"detail-label"},Zs={class:"prompt-preview"},xs={class:"dialog-content"},ea={class:"tabs-nav"},ta={class:"tabs-content"},sa={class:"tab-panel"},aa={class:"form-group"},oa={class:"form-group"},la={class:"form-group"},na={value:"pipeline"},ia={value:"graph"},da={value:"council"},ra={key:0,class:"form-group"},ca={class:"toggle-wrapper"},ua={class:"toggle-content"},ma={class:"toggle-title"},pa={class:"toggle-hint"},va={class:"form-group"},ga={class:"toggle-wrapper"},_a={class:"toggle-content"},ha={class:"toggle-title"},fa={class:"toggle-hint"},ya={key:0,class:"tab-panel"},ba={class:"toggle-header"},$a={class:"toggle-label"},ka={class:"toggle-content-large"},wa={class:"toggle-text"},Ca={class:"toggle-hint"},Ma={key:0,class:"config-badge"},za={key:0,class:"model-config-section"},Sa={class:"model-config-toolbar"},Ta={class:"model-config-copy"},Va={class:"form-grid"},Da={class:"form-group"},Ua={class:"form-group"},Aa={class:"advanced-config"},La={class:"advanced-content"},Pa={class:"form-group"},Ba=["placeholder"],Ea={class:"form-hint"},Na={class:"form-group"},Ha=["placeholder"],Oa={class:"form-hint"},Fa={class:"form-group"},Ra=["disabled"],Ga={key:1,class:"empty-state-inline"},ja={class:"empty-text"},qa={class:"dialog-content"},Ia={class:"form-group"},Ja=["placeholder"],Wa={class:"form-hint"},Ka={key:0,class:"form-group"},Xa=["placeholder"],Ya={class:"form-hint"},Qa={key:1,class:"form-group"},Za=["placeholder"],xa={key:2,class:"form-group"},eo=["placeholder"],to={class:"form-hint"},so={key:3,class:"form-group"},ao={class:"dependency-selector"},oo={key:0,class:"selected-tags"},lo=["onClick"],no=["disabled"],io={value:""},ro=["value"],co={class:"form-hint"},uo={key:4,class:"form-group"},mo={key:0,class:"condition-disabled-hint"},po={key:1,class:"condition-config"},vo={class:"toggle-wrapper"},go={class:"toggle-content"},_o={class:"toggle-title"},ho={class:"toggle-hint"},fo={key:0,class:"condition-form"},yo={class:"form-row"},bo={class:"form-col"},$o={value:"output_contains"},ko={value:"output_not_contains"},wo={class:"form-col"},Co={value:""},Mo=["value"],zo={class:"form-hint"},So={class:"form-row"},To={class:"form-col full"},Vo=["placeholder"],Do={class:"form-hint"},Uo={class:"form-group"},Ao=["placeholder"],Lo={class:"form-hint"},Po=["disabled"],Bo=be({__name:"TeamDetail",props:{team:{}},emits:["back","updated"],setup(y,{emit:p}){const m=y,F=p,{t:C}=Je(),V=Qe(),W=ct(),K=Ze(),O=At(),{confirm:U}=Ye(),N={pipeline:C("teams.detail.modePipeline"),graph:C("teams.detail.modeGraph"),council:C("teams.detail.modeCouncil")},k=T([]),oe=T(!1),X=T(!1),H=T("basic"),A=T({name:"",description:"",mode:"council",cross_review:!0,enable_skills:!1}),I=T(!1),ae=T(!1),v=T(null),_=T([]),D=T(!1),h=()=>Ve(),d=T(h()),L=T(h()),j=Z(()=>_.value.map(t=>({value:t.id,label:t.name}))),P=T(!1),b=T(null),u=T({id:"",role:"",perspective:"",task:"",system_prompt:"",depends_on_str:"",enable_condition:!1,condition_type:"output_contains",condition_node:"",condition_text:""}),ne=Z(()=>u.value.id.trim()?m.team.mode==="council"?!!u.value.perspective.trim():!!u.value.role.trim():!1);Ae(()=>m.team,t=>{t&&(k.value=JSON.parse(JSON.stringify(t.agents||[])),A.value={name:t.name,description:t.description||"",mode:t.mode,cross_review:t.cross_review,enable_skills:t.enable_skills||!1})},{immediate:!0}),We(()=>J(this,null,function*(){yield R(),yield ve()}));const ke=()=>{b.value=null,u.value={id:`agent${k.value.length+1}`,role:"",perspective:"",task:"",system_prompt:"",depends_on_str:"",enable_condition:!1,condition_type:"output_contains",condition_node:"",condition_text:""},P.value=!0},we=t=>{var f,G,Y;b.value=t;const o=k.value[t],n=!!o.condition;u.value={id:o.id,role:o.role||"",perspective:o.perspective||"",task:o.task||"",system_prompt:o.system_prompt||"",depends_on_str:(o.depends_on||[]).join(", "),enable_condition:n,condition_type:((f=o.condition)==null?void 0:f.type)||"output_contains",condition_node:((G=o.condition)==null?void 0:G.node)||"",condition_text:((Y=o.condition)==null?void 0:Y.text)||""},P.value=!0},Ce=()=>{const t=new Set,o=[];for(u.value.depends_on_str.split(",").map(f=>f.trim()).filter(Boolean).forEach(f=>{t.add(f),o.push(f)});o.length>0;){const f=o.shift(),G=k.value.find(Y=>Y.id===f);G!=null&&G.depends_on&&G.depends_on.forEach(Y=>{t.has(Y)||(t.add(Y),o.push(Y))})}return Array.from(t)},he=t=>k.value.find(o=>o.id===t),ie=()=>u.value.depends_on_str.split(",").map(t=>t.trim()).filter(Boolean),de=()=>{const t=u.value.id.trim(),o=ie();return k.value.filter(n=>{if(b.value!==null){const f=k.value[b.value];if(n.id===(f==null?void 0:f.id))return!1}return n.id===t?!1:!o.includes(n.id)})},Me=t=>{const o=t.target,n=o.value;if(!n)return;const f=ie();f.push(n),u.value.depends_on_str=f.join(", "),o.value=""},a=t=>{const n=ie().filter(f=>f!==t);u.value.depends_on_str=n.join(", "),n.length===0&&(u.value.enable_condition=!1,u.value.condition_node="",u.value.condition_text="")},c=t=>J(this,null,function*(){(yield U({title:C("teams.detail.confirmDelete"),message:C("teams.detail.confirmDeleteMessage"),type:"danger",confirmText:C("common.delete"),confirmVariant:"danger"}))&&(k.value.splice(t,1),Pe())}),i=()=>{P.value=!1,b.value=null},M=()=>{const t={id:u.value.id.trim()};if(m.team.mode==="council"){t.perspective=u.value.perspective.trim();const o=t.perspective.split(/[，,]/);t.role=o[0].trim()||t.id}else t.role=u.value.role.trim(),t.task=u.value.task.trim();u.value.system_prompt.trim()&&(t.system_prompt=u.value.system_prompt.trim()),m.team.mode==="graph"?(t.depends_on=u.value.depends_on_str.split(",").map(o=>o.trim()).filter(Boolean),u.value.enable_condition&&u.value.condition_node&&u.value.condition_text.trim()&&(t.condition={type:u.value.condition_type,node:u.value.condition_node,text:u.value.condition_text.trim()})):t.depends_on=[],b.value!==null?k.value[b.value]=t:k.value.push(t),i(),Pe()};function R(){return J(this,null,function*(){try{const t=yield O.listProviders();_.value=t.map(o=>({id:o.id,name:o.name,defaultApiBase:Pt(o),defaultModel:Lt(o)})),ge()}catch(t){}})}function ve(){return J(this,null,function*(){if(!(!m.team.id||!W.isAdmin))try{const t=yield Te.getConfig(m.team.id);L.value=Mt(void 0,t.global_defaults),t.use_custom_model?re(t.model_settings,!0):re(t.global_defaults,!1)}catch(t){}})}function re(t,o){D.value=!0;try{I.value=o,d.value=Ve(L.value,o?t:void 0),v.value=null,ge()}finally{D.value=!1}}function ge(){if(_.value.length===0||Bt(_.value,d.value.provider))return;const n=Et(_.value)||_.value[0];n&&(d.value.provider=n.id,d.value.api_base||(d.value.api_base=n.defaultApiBase||""),(!d.value.model||d.value.model===zt.model)&&(d.value.model=n.defaultModel||d.value.model))}function ze(){if(!I.value){v.value=null;return}d.value=Ve(L.value,d.value),v.value=null}function x(){return J(this,null,function*(){var t,o;ae.value=!0,v.value=null;try{const n=yield O.testConnection(Ne({provider:d.value.provider||"zhipu",api_key:d.value.api_key||void 0,api_base:d.value.api_base||void 0,model:d.value.model||"glm-5"},Tt(d.value)));v.value={success:n.success,message:n.success?n.message||C("settings.providers.testSuccess"):n.error||n.message||C("settings.providers.testFailed")}}catch(n){v.value={success:!1,message:((o=(t=n.response)==null?void 0:t.data)==null?void 0:o.error)||n.message||C("settings.providers.testFailed")}}finally{ae.value=!1}})}Ae(()=>d.value.provider,(t,o)=>{if(!t||_.value.length===0||D.value)return;const n=_.value.find(ue=>ue.id===t),f=o?_.value.find(ue=>ue.id===o):null;if(!n)return;(!d.value.api_base||!!(f!=null&&f.defaultApiBase)&&d.value.api_base===f.defaultApiBase)&&(d.value.api_base=n.defaultApiBase||""),(!d.value.model||!!(f!=null&&f.defaultModel)&&d.value.model===f.defaultModel)&&n.defaultModel&&(d.value.model=n.defaultModel)});const ce=()=>{X.value=!1,H.value="basic"},xe=()=>J(this,null,function*(){try{yield V.updateTeam(m.team.id,{name:A.value.name,description:A.value.description,mode:A.value.mode,cross_review:A.value.cross_review,enable_skills:A.value.enable_skills,agents:k.value,is_active:m.team.is_active}),W.isAdmin&&(I.value?yield Te.updateConfig(m.team.id,Vt(d.value,L.value)):m.team.use_custom_model&&(yield Te.resetConfig(m.team.id))),K.success(C("teams.detail.teamUpdated")),ce(),F("updated")}catch(t){K.error(t.message||C("teams.detail.saveFailed"))}}),Pe=()=>J(this,null,function*(){try{yield V.updateTeam(m.team.id,{name:m.team.name,description:m.team.description,mode:m.team.mode,cross_review:m.team.cross_review,enable_skills:m.team.enable_skills||!1,agents:k.value,is_active:m.team.is_active}),K.success(C("teams.detail.memberUpdated")),F("updated")}catch(t){K.error(t.message||C("teams.detail.saveFailed"))}});return(t,o)=>(l(),r("div",ps,[e("div",vs,[e("button",{class:"btn-back",onClick:o[0]||(o[0]=n=>t.$emit("back"))},[(l(),$(w(g(ut)),{size:16})),E(" "+s(t.$t("teams.detail.backToList")),1)]),e("div",gs,[e("div",_s,[e("h2",null,s(y.team.name),1),e("div",hs,[e("span",fs,s(N[y.team.mode]),1),y.team.mode==="council"?(l(),r("span",{key:0,class:ee(["badge badge-review",y.team.cross_review?"badge-cross":"badge-independent"])},s(y.team.cross_review?t.$t("teams.detail.crossMode"):t.$t("teams.detail.independentMode")),3)):z("",!0)]),e("button",{class:"icon-btn",onClick:o[1]||(o[1]=n=>X.value=!0)},[(l(),$(w(g(He)),{size:16}))])]),y.team.description?(l(),r("p",ys,s(y.team.description),1)):z("",!0)])]),e("div",bs,[e("div",$s,[e("h3",null,s(t.$t("teams.detail.membersTitle",{n:k.value.length})),1),e("div",ks,[y.team.mode==="graph"&&k.value.length>0?(l(),r("button",{key:0,class:"btn-secondary",onClick:o[2]||(o[2]=n=>oe.value=!oe.value)},[(l(),$(w(g(mt)),{size:16})),E(" "+s(oe.value?t.$t("teams.detail.hideGraph"):t.$t("teams.detail.showGraph")),1)])):z("",!0),e("button",{class:"btn-primary",onClick:ke},[(l(),$(w(g(Ke)),{size:16})),E(" "+s(t.$t("teams.detail.addMember")),1)])])]),y.team.mode==="graph"&&oe.value&&k.value.length>0?(l(),r("div",ws,[q(ms,{agents:k.value},null,8,["agents"])])):z("",!0),k.value.length===0?(l(),r("div",Cs,[(l(),$(w(g(fe)),{size:48,class:"empty-icon"})),e("p",null,s(t.$t("teams.detail.emptyMembers")),1)])):(l(),r("div",Ms,[(l(!0),r(te,null,se(k.value,(n,f)=>{var G;return l(),r("div",{key:f,class:"member-card"},[e("div",zs,[e("div",Ss,[e("span",Ts,"#"+s(f+1),1),e("h4",null,s(n.role||n.perspective||n.id),1)]),e("div",Vs,[e("button",{class:"icon-btn",onClick:Y=>we(f)},[(l(),$(w(g(He)),{size:16}))],8,Ds),e("button",{class:"icon-btn danger",onClick:Y=>c(f)},[(l(),$(w(g(Xe)),{size:16}))],8,Us)])]),e("div",As,[e("div",Ls,[o[30]||(o[30]=e("span",{class:"detail-label"},"ID:",-1)),e("span",Ps,s(n.id),1)]),y.team.mode==="council"?(l(),r("div",Bs,[e("span",Es,s(t.$t("teams.detail.perspectiveLabel")),1),e("span",Ns,s(n.perspective||"-"),1)])):(l(),r("div",Hs,[e("span",Os,s(t.$t("teams.detail.taskLabel")),1),e("span",Fs,s(n.task||"-"),1)])),y.team.mode==="graph"&&((G=n.depends_on)!=null&&G.length)?(l(),r("div",Rs,[e("span",Gs,s(t.$t("teams.detail.dependsLabel")),1),e("span",js,s(n.depends_on.join(", ")),1)])):z("",!0),n.condition?(l(),r("div",qs,[e("span",Is,s(t.$t("teams.detail.conditionLabel")),1),e("div",Js,[e("span",Ws,s(n.condition.type==="output_contains"?t.$t("teams.detail.conditionContains"):t.$t("teams.detail.conditionNotContains")),1),e("span",Ks,s(n.condition.node),1),e("span",Xs,'"'+s(n.condition.text)+'"',1)])])):z("",!0),n.system_prompt?(l(),r("div",Ys,[e("span",Qs,s(t.$t("teams.detail.systemPromptLabel")),1),e("div",Zs,s(n.system_prompt),1)])):z("",!0)])])}),128))]))]),q(g(ye),{"model-value":X.value,title:t.$t("teams.detail.editTitle"),size:"large",onClose:ce},{footer:le(()=>[e("button",{class:"co-btn co-btn--secondary",onClick:ce},s(t.$t("common.cancel")),1),e("button",{class:"co-btn co-btn--primary",onClick:xe},s(t.$t("common.save")),1)]),default:le(()=>{var n,f,G,Y,ue;return[e("div",xs,[e("div",ea,[e("button",{class:ee(["tab-btn",{active:H.value==="basic"}]),onClick:o[3]||(o[3]=S=>H.value="basic")},[(l(),$(w(g(Oe)),{size:16})),e("span",null,s(t.$t("teams.detail.tabBasic")),1)],2),g(W).isAdmin?(l(),r("button",{key:0,class:ee(["tab-btn",{active:H.value==="model"}]),onClick:o[4]||(o[4]=S=>H.value="model")},[(l(),$(w(g(pt)),{size:16})),e("span",null,s(t.$t("teams.detail.tabModel")),1)],2)):z("",!0)]),e("div",ta,[B(e("div",sa,[e("div",aa,[e("label",null,[E(s(t.$t("teams.detail.teamName"))+" ",1),o[31]||(o[31]=e("span",{class:"required"},"*",-1))]),B(e("input",{"onUpdate:modelValue":o[5]||(o[5]=S=>A.value.name=S),type:"text",class:"form-input"},null,512),[[Q,A.value.name]])]),e("div",oa,[e("label",null,s(t.$t("teams.detail.teamDescription")),1),B(e("textarea",{"onUpdate:modelValue":o[6]||(o[6]=S=>A.value.description=S),class:"form-textarea",rows:"3"},null,512),[[Q,A.value.description]])]),e("div",la,[e("label",null,[E(s(t.$t("teams.detail.collaborationMode"))+" ",1),o[32]||(o[32]=e("span",{class:"required"},"*",-1))]),B(e("select",{"onUpdate:modelValue":o[7]||(o[7]=S=>A.value.mode=S),class:"form-select"},[e("option",na,s(t.$t("teams.detail.modePipeline")),1),e("option",ia,s(t.$t("teams.detail.modeGraph")),1),e("option",da,s(t.$t("teams.detail.modeCouncil")),1)],512),[[_e,A.value.mode]])]),A.value.mode==="council"?(l(),r("div",ra,[e("div",ca,[e("div",ua,[e("span",ma,s(t.$t("teams.detail.crossReview")),1),e("p",pa,s(t.$t("teams.detail.crossReviewHint")),1)]),q(pe,{modelValue:A.value.cross_review,"onUpdate:modelValue":o[8]||(o[8]=S=>A.value.cross_review=S),width:44,height:24,"aria-label":t.$t("teams.detail.crossReview")},null,8,["modelValue","aria-label"])])])):z("",!0),e("div",va,[e("div",ga,[e("div",_a,[e("span",ha,s(t.$t("teams.detail.skills")),1),e("p",fa,s(t.$t("teams.detail.skillsHint")),1)]),q(pe,{modelValue:A.value.enable_skills,"onUpdate:modelValue":o[9]||(o[9]=S=>A.value.enable_skills=S),width:44,height:24,"aria-label":t.$t("teams.detail.skills")},null,8,["modelValue","aria-label"])])])],512),[[Fe,H.value==="basic"]]),g(W).isAdmin?B((l(),r("div",ya,[e("div",{class:ee(["config-toggle",{active:I.value}])},[e("div",ba,[e("label",$a,[q(pe,{modelValue:I.value,"onUpdate:modelValue":o[10]||(o[10]=S=>I.value=S),width:48,height:28,"aria-label":t.$t("teams.detail.customModel"),onChange:ze},null,8,["modelValue","aria-label"]),e("div",ka,[e("span",wa,s(t.$t("teams.detail.customModel")),1),e("span",Ca,s(t.$t("teams.detail.customModelHint")),1)])]),I.value?(l(),r("div",Ma,[(l(),$(w(g(vt)),{size:14})),e("span",null,s(t.$t("teams.detail.custom")),1)])):z("",!0)])],2),I.value?(l(),r("div",za,[e("div",Sa,[e("div",Ta,[e("h4",null,s(t.$t("teams.detail.modelSettings")),1)])]),e("div",Va,[e("div",Da,[e("label",null,s(t.$t("settings.providers.selectProvider")),1),q(St,{modelValue:d.value.provider,"onUpdate:modelValue":o[11]||(o[11]=S=>d.value.provider=S),options:j.value,placeholder:t.$t("settings.providers.selectProvider"),searchable:""},null,8,["modelValue","options","placeholder"])]),e("div",Ua,[e("label",null,s(t.$t("settings.providers.model")),1),B(e("input",{"onUpdate:modelValue":o[12]||(o[12]=S=>d.value.model=S),type:"text",class:"form-input",placeholder:"glm-5"},null,512),[[Q,d.value.model]])])]),q(Dt,{temperature:(n=d.value.temperature)!=null?n:0,"max-tokens":(f=d.value.max_tokens)!=null?f:0,"max-iterations":(G=d.value.max_iterations)!=null?G:0,"thinking-enabled":(Y=d.value.thinking_enabled)!=null?Y:!0,"stream-enabled":(ue=d.value.stream_enabled)!=null?ue:!0,"onUpdate:temperature":o[13]||(o[13]=S=>d.value.temperature=S),"onUpdate:maxTokens":o[14]||(o[14]=S=>d.value.max_tokens=S),"onUpdate:maxIterations":o[15]||(o[15]=S=>d.value.max_iterations=S),"onUpdate:thinkingEnabled":o[16]||(o[16]=S=>d.value.thinking_enabled=S),"onUpdate:streamEnabled":o[17]||(o[17]=S=>d.value.stream_enabled=S)},null,8,["temperature","max-tokens","max-iterations","thinking-enabled","stream-enabled"]),e("details",Aa,[e("summary",null,[(l(),$(w(g(gt)),{size:16})),e("span",null,s(t.$t("chat.sessionConfig.advancedApiSettings")),1),(l(),$(w(g(_t)),{size:16,class:"chevron"}))]),e("div",La,[e("div",Pa,[e("label",null,s(t.$t("settings.providers.apiKey")),1),B(e("input",{"onUpdate:modelValue":o[18]||(o[18]=S=>d.value.api_key=S),type:"password",placeholder:t.$t("chat.sessionConfig.leaveEmptyForGlobal"),class:"form-input"},null,8,Ba),[[Q,d.value.api_key]]),e("p",Ea,s(t.$t("chat.sessionConfig.apiKeyHint")),1)]),e("div",Na,[e("label",null,s(t.$t("settings.providers.baseUrl")),1),B(e("input",{"onUpdate:modelValue":o[19]||(o[19]=S=>d.value.api_base=S),type:"text",placeholder:t.$t("chat.sessionConfig.leaveEmptyForGlobal"),class:"form-input"},null,8,Ha),[[Q,d.value.api_base]]),e("p",Oa,s(t.$t("chat.sessionConfig.apiBaseHint")),1)]),e("div",Fa,[e("button",{onClick:x,class:"btn-secondary",disabled:ae.value},[(l(),$(w(ae.value?g(ht):g(Re)),{size:16,class:ee({spin:ae.value})},null,8,["class"])),e("span",null,s(ae.value?t.$t("settings.providers.testing"):t.$t("settings.providers.testConnection")),1)],8,Ra)]),v.value?(l(),r("div",{key:0,class:ee(["test-result",v.value.success?"success":"error"])},[(l(),$(w(v.value.success?g(Re):g(ft)),{size:16})),e("span",null,s(v.value.message),1)],2)):z("",!0)])])])):(l(),r("div",Ga,[(l(),$(w(g(yt)),{size:32,class:"empty-icon"})),e("div",ja,[e("h4",null,s(t.$t("teams.detail.globalDefault")),1),e("p",null,s(t.$t("teams.detail.globalDefaultHint")),1)])]))],512)),[[Fe,H.value==="model"]]):z("",!0)])])]}),_:1},8,["model-value","title"]),q(g(ye),{"model-value":P.value,title:b.value===null?t.$t("teams.detail.addMemberTitle"):t.$t("teams.detail.editMemberTitle"),size:"large",onClose:i},{footer:le(()=>[e("button",{class:"co-btn co-btn--secondary",onClick:i},s(t.$t("common.cancel")),1),e("button",{class:"co-btn co-btn--primary",onClick:M,disabled:!ne.value},s(t.$t("common.save")),9,Po)]),default:le(()=>[e("div",qa,[e("div",Ia,[e("label",null,[E(s(t.$t("teams.detail.memberId"))+" ",1),o[33]||(o[33]=e("span",{class:"required"},"*",-1))]),B(e("input",{"onUpdate:modelValue":o[20]||(o[20]=n=>u.value.id=n),type:"text",class:"form-input",placeholder:t.$t("teams.detail.memberIdPlaceholder")},null,8,Ja),[[Q,u.value.id]]),e("p",Wa,s(t.$t("teams.detail.memberIdHint")),1)]),y.team.mode==="council"?(l(),r("div",Ka,[e("label",null,[E(s(t.$t("teams.detail.perspective"))+" ",1),o[34]||(o[34]=e("span",{class:"required"},"*",-1))]),B(e("input",{"onUpdate:modelValue":o[21]||(o[21]=n=>u.value.perspective=n),type:"text",class:"form-input",placeholder:t.$t("teams.detail.perspectivePlaceholder")},null,8,Xa),[[Q,u.value.perspective]]),e("p",Ya,s(t.$t("teams.detail.perspectiveHint")),1)])):(l(),r("div",Qa,[e("label",null,[E(s(t.$t("teams.detail.role"))+" ",1),o[35]||(o[35]=e("span",{class:"required"},"*",-1))]),B(e("input",{"onUpdate:modelValue":o[22]||(o[22]=n=>u.value.role=n),type:"text",class:"form-input",placeholder:t.$t("teams.detail.rolePlaceholder")},null,8,Za),[[Q,u.value.role]])])),y.team.mode!=="council"?(l(),r("div",xa,[e("label",null,s(t.$t("teams.detail.task")),1),B(e("textarea",{"onUpdate:modelValue":o[23]||(o[23]=n=>u.value.task=n),class:"form-textarea",rows:"3",placeholder:t.$t("teams.detail.taskPlaceholder")},null,8,eo),[[Q,u.value.task]]),e("p",to,s(t.$t("teams.detail.taskHint")),1)])):z("",!0),y.team.mode==="graph"?(l(),r("div",so,[e("label",null,s(t.$t("teams.detail.dependsOn")),1),e("div",ao,[ie().length>0?(l(),r("div",oo,[(l(!0),r(te,null,se(ie(),n=>(l(),r("span",{key:n,class:"dependency-tag"},[E(s(n)+" ",1),e("button",{type:"button",class:"tag-remove",onClick:f=>a(n)},"×",8,lo)]))),128))])):z("",!0),e("select",{class:"form-select",onChange:o[24]||(o[24]=n=>Me(n)),disabled:de().length===0},[e("option",io,s(de().length===0?t.$t("teams.detail.noDependencies"):t.$t("teams.detail.selectDependencies")),1),(l(!0),r(te,null,se(de(),n=>(l(),r("option",{key:n.id,value:n.id},s(n.id)+" - "+s(n.role||n.perspective||t.$t("teams.detail.unnamed")),9,ro))),128))],40,no)]),e("p",co,s(t.$t("teams.detail.dependsHint")),1)])):z("",!0),y.team.mode==="graph"?(l(),r("div",uo,[e("label",null,s(t.$t("teams.detail.conditionOptional")),1),u.value.depends_on_str.trim()?(l(),r("div",po,[e("div",vo,[e("div",go,[e("span",_o,s(t.$t("teams.detail.enableCondition")),1),e("p",ho,s(t.$t("teams.detail.conditionHint")),1)]),q(pe,{modelValue:u.value.enable_condition,"onUpdate:modelValue":o[25]||(o[25]=n=>u.value.enable_condition=n),width:44,height:24,"aria-label":t.$t("teams.detail.enableCondition")},null,8,["modelValue","aria-label"])]),u.value.enable_condition?(l(),r("div",fo,[e("div",yo,[e("div",bo,[e("label",null,s(t.$t("teams.detail.conditionType")),1),B(e("select",{"onUpdate:modelValue":o[26]||(o[26]=n=>u.value.condition_type=n),class:"form-select"},[e("option",$o,s(t.$t("teams.detail.outputContains")),1),e("option",ko,s(t.$t("teams.detail.outputNotContains")),1)],512),[[_e,u.value.condition_type]])]),e("div",wo,[e("label",null,s(t.$t("teams.detail.checkNode")),1),B(e("select",{"onUpdate:modelValue":o[27]||(o[27]=n=>u.value.condition_node=n),class:"form-select"},[e("option",Co,s(t.$t("teams.detail.selectNode")),1),(l(!0),r(te,null,se(Ce(),n=>{var f,G;return l(),r("option",{key:n,value:n},s(n)+" - "+s(((f=he(n))==null?void 0:f.role)||((G=he(n))==null?void 0:G.perspective)||t.$t("teams.detail.unnamed")),9,Mo)}),128))],512),[[_e,u.value.condition_node]]),e("p",zo,s(t.$t("teams.detail.anyUpstream")),1)])]),e("div",So,[e("div",To,[e("label",null,s(t.$t("teams.detail.matchText")),1),B(e("input",{"onUpdate:modelValue":o[28]||(o[28]=n=>u.value.condition_text=n),type:"text",class:"form-input",placeholder:t.$t("teams.detail.matchPlaceholder")},null,8,Vo),[[Q,u.value.condition_text]]),e("p",Do,s(u.value.condition_type==="output_contains"?t.$t("teams.detail.matchContainsHint"):t.$t("teams.detail.matchNotContainsHint")),1)])])])):z("",!0)])):(l(),r("div",mo,[(l(),$(w(g(Oe)),{size:16})),e("span",null,s(t.$t("teams.detail.selectDependenciesFirst")),1)]))])):z("",!0),e("div",Uo,[e("label",null,s(t.$t("teams.detail.systemPromptFull")),1),B(e("textarea",{"onUpdate:modelValue":o[29]||(o[29]=n=>u.value.system_prompt=n),class:"form-textarea prompt-textarea",rows:"8",placeholder:t.$t("teams.detail.systemPromptPlaceholder")},null,8,Ao),[[Q,u.value.system_prompt]]),e("p",Lo,s(t.$t("teams.detail.systemPromptHint")),1)])])]),_:1},8,["model-value","title"])]))}}),Eo=$e(Bo,[["__scopeId","data-v-e28f89ae"]]),qe=[{id:"document-analysis-pipeline",name:"文档深度分析",description:"理解文档 → 提取要点 → 分析问题 → 生成总结报告",category:"文档处理",mode:"pipeline",cross_review:!1,enable_skills:!0,agents:[{id:"reader",role:"文档理解专家",task:"通读文档，理解整体结构和核心内容",system_prompt:`你是文档理解专家，擅长快速把握文档的核心内容和结构。

你的任务：
1. 识别文档类型（技术文档、商业报告、学术论文等）
2. 梳理文档的整体结构和章节关系
3. 提取文档的核心主题和关键概念
4. 标注重要段落和关键信息的位置

输出格式：
- 文档类型：[类型]
- 核心主题：[主题描述]
- 结构概览：[章节列表]
- 关键概念：[概念列表]
- 重点段落：[段落索引和摘要]`},{id:"extractor",role:"信息提取专家",task:"从文档中提取关键信息、数据和观点",system_prompt:`你是信息提取专家，善于从文档中挖掘有价值的信息。

你的任务：
1. 提取所有关键数据、指标和统计信息
2. 识别作者的核心观点和论据
3. 提取重要的定义、公式和规则
4. 标注引用、参考文献和外部资源

输出格式：
- 关键数据：[数据列表，包含数值、单位、上下文]
- 核心观点：[观点列表，包含论据支持]
- 重要定义：[术语和定义]
- 引用来源：[引用列表]`},{id:"analyzer",role:"批判性分析专家",task:"分析文档的逻辑性、完整性和潜在问题",system_prompt:`你是批判性思维专家，善于发现文档中的问题和改进空间。

你的任务：
1. 评估论证的逻辑性和严密性
2. 识别信息缺口和未解答的问题
3. 发现潜在的偏见、假设和局限性
4. 提出质疑和需要进一步验证的点

输出格式：
- 逻辑评估：[论证链分析]
- 信息缺口：[缺失的关键信息]
- 潜在问题：[偏见、假设、局限性]
- 质疑点：[需要验证的内容]`},{id:"summarizer",role:"报告撰写专家",task:"整合前序分析，生成结构化的分析报告",system_prompt:`你是报告撰写专家，善于将复杂分析整合为清晰的报告。

你的任务：
1. 综合前面所有分析结果
2. 按重要性组织信息
3. 用清晰的语言表达复杂概念
4. 提供可操作的结论和建议

输出格式：
# 文档分析报告

## 执行摘要
[一段话总结核心发现]

## 文档概览
[文档类型、主题、结构]

## 关键发现
[最重要的信息和数据]

## 深度分析
[逻辑评估、问题识别]

## 结论与建议
[总结性结论和行动建议]`}]},{id:"content-creation-pipeline",name:"专业内容创作",description:"受众分析 → 大纲设计 → 内容撰写 → 质量把关",category:"内容创作",mode:"pipeline",cross_review:!1,enable_skills:!0,agents:[{id:"audience-analyst",role:"受众分析师",task:"分析目标受众的需求、痛点和期望",system_prompt:`你是受众分析专家，深入理解不同用户群体的需求。

分析维度：
1. 目标受众画像（年龄、职业、知识水平）
2. 核心需求和痛点
3. 阅读习惯和偏好
4. 期望获得的价值

输出：受众分析报告，包含具体的内容建议`},{id:"outline-designer",role:"内容架构师",task:"设计内容结构和逻辑框架",system_prompt:`你是内容架构专家，擅长设计引人入胜的内容结构。

设计要点：
1. 开篇：如何吸引注意力
2. 主体：逻辑递进的论述结构
3. 案例：何时插入例子和数据
4. 结尾：如何强化核心信息

输出：详细的内容大纲，标注每部分的目的和要点`},{id:"writer",role:"内容创作者",task:"基于大纲撰写高质量内容",system_prompt:`你是专业内容创作者，文笔流畅，善于讲故事。

写作原则：
1. 开篇引人入胜，快速切入主题
2. 使用具体例子和数据支撑观点
3. 保持逻辑清晰，段落间平滑过渡
4. 语言简洁有力，避免冗余
5. 结尾呼应开篇，强化核心信息

输出：完整的内容初稿`},{id:"editor",role:"内容编辑",task:"审核内容质量，优化表达和结构",system_prompt:`你是资深内容编辑，对语言和逻辑有敏锐的感知。

审核清单：
1. 事实准确性：数据、引用是否正确
2. 逻辑连贯性：论证是否严密
3. 语言质量：是否有语法错误、表达不当
4. 可读性：是否易于理解，节奏是否合适
5. 价值传递：是否真正解决了受众的问题

输出：修改建议和最终版本`}]},{id:"code-quality-check-graph",name:"代码质量检查系统",description:"并行检查多个维度，根据问题严重程度决定是否需要重构建议",category:"软件开发",mode:"graph",cross_review:!1,enable_skills:!0,agents:[{id:"syntax-checker",role:"语法检查器",task:"检查代码语法错误和基本规范",depends_on:[],system_prompt:`你是代码语法检查专家。

检查项：
1. 语法错误
2. 命名规范
3. 代码格式
4. 基本的代码规范

输出：问题列表，标注严重程度（严重/警告/建议）`},{id:"logic-analyzer",role:"逻辑分析器",task:"分析代码逻辑和潜在bug",depends_on:[],system_prompt:`你是代码逻辑分析专家。

分析项：
1. 逻辑错误和边界条件
2. 空指针和异常处理
3. 资源泄漏风险
4. 并发安全问题

输出：问题列表，标注严重程度和影响范围`},{id:"performance-analyzer",role:"性能分析器",task:"分析性能瓶颈和优化机会",depends_on:[],system_prompt:`你是性能分析专家。

分析项：
1. 算法复杂度
2. 不必要的循环和计算
3. 数据库查询效率
4. 内存使用

输出：性能问题列表和优化建议`},{id:"summary-reporter",role:"问题汇总",task:"汇总所有检查结果，生成综合报告",depends_on:["syntax-checker","logic-analyzer","performance-analyzer"],system_prompt:`你是质量报告专家，整合所有检查结果。

任务：
1. 按严重程度排序所有问题
2. 识别最关键的问题
3. 评估整体代码质量
4. 判断是否需要重构（如果严重问题超过3个，输出"需要重构"）

输出：综合质量报告`},{id:"refactor-advisor",role:"重构建议专家",task:"提供详细的重构方案（仅在问题严重时执行）",depends_on:["summary-reporter"],condition:{type:"output_contains",node:"summary-reporter",text:"需要重构"},system_prompt:`你是代码重构专家，提供系统的重构方案。

重构方案包括：
1. 重构优先级和顺序
2. 具体的重构步骤
3. 重构后的预期改进
4. 风险和注意事项

输出：详细的重构计划`}]},{id:"problem-diagnosis-graph",name:"问题诊断系统",description:"并行收集信息，综合诊断，根据问题类型提供不同的解决方案",category:"问题诊断",mode:"graph",cross_review:!1,enable_skills:!0,agents:[{id:"symptom-collector",role:"症状收集",task:"收集和整理问题的表现症状",depends_on:[],system_prompt:`你是问题症状收集专家。

收集内容：
1. 问题的具体表现
2. 发生的时间和频率
3. 影响范围和严重程度
4. 用户的操作步骤

输出：结构化的症状清单`},{id:"context-analyzer",role:"环境分析",task:"分析问题发生的环境和上下文",depends_on:[],system_prompt:`你是环境分析专家。

分析内容：
1. 系统环境（版本、配置）
2. 数据状态
3. 相关的变更记录
4. 外部依赖状态

输出：环境分析报告`},{id:"root-cause-analyzer",role:"根因分析",task:"基于症状和环境，分析问题的根本原因",depends_on:["symptom-collector","context-analyzer"],system_prompt:`你是根因分析专家，使用5-Why方法深入分析。

分析方法：
1. 列出所有可能的原因
2. 逐层深入追问"为什么"
3. 识别根本原因
4. 判断问题类型（配置问题/代码bug/设计缺陷/外部因素）

输出：根因分析报告，明确标注问题类型`},{id:"quick-fix-provider",role:"快速修复方案",task:"提供临时解决方案（配置问题或外部因素）",depends_on:["root-cause-analyzer"],condition:{type:"output_contains",node:"root-cause-analyzer",text:"配置问题"},system_prompt:`你是快速修复专家，提供立即可用的解决方案。

方案内容：
1. 具体的修复步骤
2. 预期效果
3. 可能的副作用
4. 验证方法

输出：快速修复指南`},{id:"code-fix-provider",role:"代码修复方案",task:"提供代码级别的修复方案（代码bug）",depends_on:["root-cause-analyzer"],condition:{type:"output_contains",node:"root-cause-analyzer",text:"bug"},system_prompt:`你是代码修复专家，提供详细的代码修复方案。

方案内容：
1. 需要修改的代码位置
2. 具体的修改内容
3. 相关的测试用例
4. 回归测试建议

输出：代码修复方案`},{id:"redesign-advisor",role:"重新设计建议",task:"提供架构或设计层面的改进建议（设计缺陷）",depends_on:["root-cause-analyzer"],condition:{type:"output_contains",node:"root-cause-analyzer",text:"设计缺陷"},system_prompt:`你是架构设计专家，提供系统性的改进方案。

方案内容：
1. 当前设计的问题分析
2. 改进的设计方案
3. 迁移路径和步骤
4. 风险评估

输出：设计改进方案`}]},{id:"solution-evaluation-council",name:"方案评估委员会",description:"多位专家独立评估技术方案，不互相影响",category:"决策支持",mode:"council",cross_review:!1,enable_skills:!1,agents:[{id:"tech-evaluator",perspective:"技术可行性评估专家，关注实现难度和技术风险",system_prompt:`你是技术可行性评估专家。

评估维度：
1. 技术成熟度和可靠性
2. 团队技术能力匹配度
3. 实现复杂度和时间估算
4. 技术债务和长期维护成本
5. 技术风险和应对方案

评分：1-10分，并说明理由
建议：通过/有条件通过/不通过`},{id:"cost-evaluator",perspective:"成本效益分析专家，关注投入产出比",system_prompt:`你是成本效益分析专家。

评估维度：
1. 初始投资成本（人力、资源、工具）
2. 运营成本（服务器、维护、支持）
3. 预期收益（效率提升、成本节约、收入增长）
4. 投资回报周期
5. 机会成本

评分：1-10分，并说明理由
建议：通过/有条件通过/不通过`},{id:"user-evaluator",perspective:"用户体验专家，关注用户价值和体验",system_prompt:`你是用户体验评估专家。

评估维度：
1. 是否真正解决用户痛点
2. 用户学习成本和使用难度
3. 对现有用户的影响
4. 用户满意度预期
5. 竞品对比优势

评分：1-10分，并说明理由
建议：通过/有条件通过/不通过`},{id:"risk-evaluator",perspective:"风险管理专家，关注各类风险和应对",system_prompt:`你是风险管理专家。

评估维度：
1. 技术风险（失败可能性、备选方案）
2. 业务风险（市场变化、竞争压力）
3. 合规风险（法律、隐私、安全）
4. 运营风险（依赖、单点故障）
5. 声誉风险（用户反馈、品牌影响）

评分：1-10分（风险越低分数越高）
建议：通过/有条件通过/不通过`}]},{id:"design-review-council",name:"设计评审委员会",description:"多位专家交叉评审设计方案，互相质疑和完善",category:"软件开发",mode:"council",cross_review:!0,enable_skills:!1,agents:[{id:"architect-reviewer",perspective:"架构师，关注系统架构的合理性和可扩展性",system_prompt:`你是资深架构师，评审系统设计方案。

评审重点：
1. 架构模式选择是否合理
2. 模块划分和职责是否清晰
3. 接口设计是否合理
4. 可扩展性和可维护性
5. 技术选型的合理性

在交叉评审中，请：
- 质疑其他评审者可能忽略的架构问题
- 补充其他视角未覆盖的架构风险
- 对其他评审者的建议提出改进意见`},{id:"security-reviewer",perspective:"安全专家，关注安全漏洞和风险",system_prompt:`你是安全专家，从安全角度评审设计。

评审重点：
1. 认证和授权机制
2. 数据加密和传输安全
3. 输入验证和注入防护
4. 敏感信息处理
5. 安全日志和审计

在交叉评审中，请：
- 指出其他评审者忽略的安全隐患
- 评估其他人提出的方案是否引入新的安全风险
- 提供更安全的替代方案`},{id:"performance-reviewer",perspective:"性能专家，关注性能瓶颈和优化",system_prompt:`你是性能优化专家，评审性能相关设计。

评审重点：
1. 数据库设计和查询效率
2. 缓存策略
3. 并发处理能力
4. 资源使用效率
5. 性能监控和优化空间

在交叉评审中，请：
- 分析其他评审者的建议对性能的影响
- 指出可能的性能瓶颈
- 提供性能优化建议`},{id:"maintainability-reviewer",perspective:"可维护性专家，关注代码质量和长期维护",system_prompt:`你是可维护性专家，关注长期维护成本。

评审重点：
1. 代码组织和模块化
2. 文档完整性
3. 测试覆盖率和测试策略
4. 技术债务风险
5. 团队技能匹配度

在交叉评审中，请：
- 评估其他评审者的建议是否增加维护复杂度
- 提出更易维护的替代方案
- 关注长期演进的可行性`}]},{id:"content-review-council",name:"内容质量评审",description:"多位编辑从不同角度评审内容质量",category:"内容创作",mode:"council",cross_review:!0,enable_skills:!1,agents:[{id:"fact-checker",perspective:"事实核查专家，确保内容准确性",system_prompt:`你是事实核查专家，确保内容的准确性。

核查重点：
1. 数据和统计信息的准确性
2. 引用来源的可靠性
3. 事实陈述是否有误
4. 时效性（信息是否过时）
5. 逻辑推理是否严密

在交叉评审中，请指出其他评审者可能忽略的事实错误`},{id:"language-editor",perspective:"语言编辑，优化表达和文字质量",system_prompt:`你是语言编辑，关注文字表达质量。

编辑重点：
1. 语法和拼写错误
2. 表达是否清晰准确
3. 语言风格是否统一
4. 句子结构和段落组织
5. 可读性和流畅度

在交叉评审中，请优化其他评审者提出的修改建议的表达`},{id:"audience-fit-reviewer",perspective:"受众匹配专家，确保内容符合目标受众",system_prompt:`你是受众匹配专家，评估内容是否适合目标读者。

评估重点：
1. 内容深度是否匹配受众水平
2. 专业术语使用是否恰当
3. 例子和类比是否贴近受众
4. 内容是否解决受众的实际问题
5. 语气和风格是否符合受众期望

在交叉评审中，请从受众角度评估其他人的修改建议`}]}],No=["全部","文档处理","内容创作","软件开发","问题诊断","决策支持"],Ho={class:"multiagent-config"},Oo={class:"teams-list-view"},Fo={class:"team-toolbar"},Ro={class:"team-stats"},Go={class:"team-stat"},jo={class:"team-stat"},qo={class:"team-actions"},Io=["disabled"],Jo={key:0,class:"team-filters"},Wo={class:"team-search"},Ko=["placeholder"],Xo={value:""},Yo={value:"pipeline"},Qo={value:"graph"},Zo={value:"council"},xo={value:""},el={value:"active"},tl={value:"inactive"},sl={key:1,class:"team-state"},al={key:2,class:"team-state"},ol={class:"team-state-desc"},ll={key:3,class:"team-empty"},nl={class:"team-empty-icon"},il={class:"team-empty-title"},dl={class:"team-empty-desc"},rl={class:"team-empty-actions"},cl={key:4,class:"team-list"},ul=["onClick"],ml={class:"team-index"},pl={class:"team-name-line"},vl={class:"team-name"},gl={class:"team-badge"},_l={key:0,class:"team-badge"},hl={key:1,class:"team-badge team-badge--muted"},fl={class:"team-member-count"},yl={class:"team-row-actions"},bl=["title","onClick"],$l=["title","onClick"],kl={key:5,class:"team-state"},wl={class:"team-state-title"},Cl={class:"team-state-desc"},Ml={class:"dialog-content"},zl={class:"template-hint"},Sl={class:"template-categories"},Tl=["onClick"],Vl={class:"templates-grid"},Dl=["onClick"],Ul={class:"template-header"},Al={class:"template-badge"},Ll={class:"template-description"},Pl={class:"template-footer"},Bl={class:"template-agents"},El={class:"template-category"},Nl={class:"agent-form"},Hl={class:"af-field"},Ol={class:"af-label",for:"team-form-name"},Fl=["placeholder"],Rl={class:"af-field"},Gl={class:"af-label",for:"team-form-desc"},jl=["placeholder"],ql={class:"af-field"},Il={class:"af-label"},Jl={class:"mode-selector"},Wl=["onUpdate:modelValue","value"],Kl={class:"mode-content"},Xl={class:"af-switches"},Yl={key:0,class:"af-switch-row"},Ql={class:"af-switch-text"},Zl={class:"af-switch-title"},xl={class:"af-switch-hint"},en={class:"af-switch-row"},tn={class:"af-switch-text"},sn={class:"af-switch-title"},an={class:"af-switch-hint"},on=["disabled"],ln=be({__name:"MultiAgentConfig",setup(y){const{t:p}=Je(),m=Qe(),F=Ze(),{confirm:C}=Ye(),V=Z(()=>m.teams),W=Z(()=>V.value.filter(a=>a.is_active).length),K=Z(()=>m.loading),O=Z(()=>m.error),U=T(!1),N=T(!1),k=T(null),oe=T(),X=T(""),H=T(""),A=T(""),I=T("全部"),ae=Z(()=>I.value==="全部"?qe:qe.filter(a=>a.category===I.value)),v=Z(()=>{let a=V.value;if(X.value.trim()){const c=X.value.toLowerCase();a=a.filter(i=>i.name.toLowerCase().includes(c)||i.description&&i.description.toLowerCase().includes(c))}if(H.value&&(a=a.filter(c=>c.mode===H.value)),A.value){const c=A.value==="active";a=a.filter(i=>i.is_active===c)}return a}),_=()=>{X.value="",H.value="",A.value=""},D=a=>{h.value={name:a.name,description:a.description,mode:a.mode,cross_review:a.cross_review,enable_skills:a.enable_skills,agents:JSON.parse(JSON.stringify(a.agents)),is_active:!0},N.value=!1,U.value=!0},h=T({name:"",description:"",mode:"council",cross_review:!0,enable_skills:!1,agents:[],is_active:!0}),d={pipeline:p("settings.multiagent.modePipeline"),graph:p("settings.multiagent.modeGraph"),council:p("settings.multiagent.modeCouncil")},L=[{id:"pipeline",name:p("settings.multiagent.modePipelineLong"),desc:p("settings.multiagent.modePipelineDesc")},{id:"graph",name:p("settings.multiagent.modeGraphLong"),desc:p("settings.multiagent.modeGraphDesc")},{id:"council",name:p("settings.multiagent.modeCouncilLong"),desc:p("settings.multiagent.modeCouncilDesc")}];We(()=>J(this,null,function*(){yield ne()}));function j(){var a;(a=oe.value)==null||a.click()}function P(){const a={version:"1.0.0",exported_at:new Date().toISOString(),teams:V.value.map(M=>({name:M.name,description:M.description||"",mode:M.mode,agents:M.agents,is_active:M.is_active,cross_review:M.cross_review,enable_skills:M.enable_skills}))},c=URL.createObjectURL(new Blob([JSON.stringify(a,null,2)],{type:"application/json"})),i=document.createElement("a");i.href=c,i.download=`agent-teams-${new Date().toISOString().slice(0,10)}.json`,i.click(),URL.revokeObjectURL(c)}function b(a){const c=String((a==null?void 0:a.name)||"").trim();if(!c)return null;const i=["pipeline","graph","council"].includes(a==null?void 0:a.mode)?a.mode:"pipeline";return{name:c,description:String((a==null?void 0:a.description)||""),mode:i,agents:(Array.isArray(a==null?void 0:a.agents)?a.agents:[]).filter(M=>M&&String(M.id||"").trim()).map(M=>{var R;return{id:String(M.id),role:String(M.role||""),system_prompt:M.system_prompt?String(M.system_prompt):null,task:String(M.task||""),perspective:M.perspective?String(M.perspective):null,depends_on:Array.isArray(M.depends_on)?M.depends_on.map(String):[],condition:(R=M.condition)!=null?R:null}}),is_active:(a==null?void 0:a.is_active)!==!1,cross_review:(a==null?void 0:a.cross_review)!==!1,enable_skills:!!(a!=null&&a.enable_skills)}}function u(a){return J(this,null,function*(){var M;const c=a.target,i=(M=c.files)==null?void 0:M[0];if(c.value="",!!i)try{const R=JSON.parse(yield i.text()),ve=Array.isArray(R)?R:R==null?void 0:R.teams;if(!Array.isArray(ve)||ve.length===0)throw new Error(p("settings.multiagent.noTeamData"));const re=ve.map(b).filter(Boolean);if(!re.length)throw new Error(p("settings.multiagent.noImportableTeams"));const ge=new Set;for(const x of re){if(ge.has(x.name))throw new Error(p("settings.multiagent.duplicateTeamName",{name:x.name}));ge.add(x.name)}const ze=new Map(V.value.map(x=>[x.name,x]));for(const x of re){const ce=ze.get(x.name);ce?yield m.updateTeam(ce.id,x):yield m.createTeam(x)}yield ne(),F.success(p("settings.multiagent.importedTeams",{n:re.length}))}catch(R){F.error((R==null?void 0:R.message)||p("settings.multiagent.importFailed"))}})}const ne=()=>J(this,null,function*(){yield m.loadTeams()}),ke=a=>{k.value=a},we=a=>{a||(k.value=null)},Ce=()=>J(this,null,function*(){if(yield m.loadTeams(),k.value){const a=V.value.find(c=>c.id===k.value.id);a&&(k.value=a)}}),he=a=>J(this,null,function*(){yield C({title:p("common.confirmDelete"),message:p("settings.multiagent.confirmDelete",{name:a.name}),type:"danger",confirmText:p("common.delete"),confirmVariant:"danger",onConfirm:()=>J(this,null,function*(){try{yield m.deleteTeam(a.id),F.success(p("common.success"))}catch(c){F.error(c.message||p("common.error"))}})})}),ie=a=>{const c={mode:a.mode,goal:p("settings.multiagent.goalPlaceholder"),cross_review:a.cross_review,agents:a.agents.map(i=>({id:i.id,role:i.role,perspective:i.perspective,task:i.task,depends_on:i.depends_on,system_prompt:i.system_prompt}))};navigator.clipboard.writeText(JSON.stringify(c,null,2)),F.success(p("common.copied"))},de=()=>{U.value=!1,h.value={name:"",description:"",mode:"council",cross_review:!0,enable_skills:!1,agents:[],is_active:!0}},Me=()=>J(this,null,function*(){if(!h.value.name.trim()){F.error(p("settings.multiagent.form.nameRequired"));return}try{const a=yield m.createTeam(h.value);F.success(p("settings.multiagent.form.createSuccess")),de(),k.value=a}catch(a){F.error(a.message||p("settings.multiagent.form.createError"))}});return(a,c)=>(l(),r("div",Ho,[e("div",Oo,[e("div",Fo,[e("div",Ro,[e("span",Go,[e("b",null,s(W.value),1),E(" "+s(a.$t("settings.multiagent.activeCount")),1)]),c[14]||(c[14]=e("span",{class:"team-stat-sep","aria-hidden":"true"},null,-1)),e("span",jo,[E(s(a.$t("settings.multiagent.totalCount"))+" ",1),e("b",null,s(V.value.length),1)])]),e("div",qo,[e("button",{class:"co-btn co-btn--secondary",onClick:j},[(l(),$(w(g(bt)),{size:14})),E(" "+s(a.$t("settings.multiagent.importTeams")),1)]),e("button",{class:"co-btn co-btn--secondary",disabled:!V.value.length,onClick:P},[(l(),$(w(g($t)),{size:14})),E(" "+s(a.$t("settings.multiagent.exportTeams")),1)],8,Io),e("button",{class:"co-btn co-btn--secondary",onClick:c[0]||(c[0]=i=>N.value=!0)},[(l(),$(w(g(Ge)),{size:14})),E(" "+s(a.$t("settings.multiagent.fromTemplate")),1)]),e("button",{class:"co-btn co-btn--primary",onClick:c[1]||(c[1]=i=>U.value=!0)},[(l(),$(w(g(Ke)),{size:14})),E(" "+s(a.$t("settings.multiagent.newTeam")),1)]),e("input",{ref_key:"importInput",ref:oe,type:"file",accept:"application/json,.json",class:"import-file-input",onChange:u},null,544)])]),V.value.length>0?(l(),r("div",Jo,[e("div",Wo,[(l(),$(w(g(je)),{size:14,class:"team-search-icon"})),B(e("input",{"onUpdate:modelValue":c[2]||(c[2]=i=>X.value=i),class:"team-search-input",type:"text",placeholder:a.$t("settings.multiagent.searchPlaceholder")},null,8,Ko),[[Q,X.value]]),X.value?(l(),r("button",{key:0,class:"team-search-clear",onClick:c[3]||(c[3]=i=>X.value="")},[(l(),$(w(g(Ie)),{size:13}))])):z("",!0)]),B(e("select",{"onUpdate:modelValue":c[4]||(c[4]=i=>H.value=i),class:"co-select team-filter"},[e("option",Xo,s(a.$t("settings.multiagent.allModes")),1),e("option",Yo,s(a.$t("settings.multiagent.modePipeline")),1),e("option",Qo,s(a.$t("settings.multiagent.modeGraph")),1),e("option",Zo,s(a.$t("settings.multiagent.modeCouncil")),1)],512),[[_e,H.value]]),B(e("select",{"onUpdate:modelValue":c[5]||(c[5]=i=>A.value=i),class:"co-select team-filter"},[e("option",xo,s(a.$t("settings.multiagent.allStatus")),1),e("option",el,s(a.$t("settings.multiagent.statusActive")),1),e("option",tl,s(a.$t("settings.multiagent.statusInactive")),1)],512),[[_e,A.value]])])):z("",!0),K.value?(l(),r("div",sl,[q(g(Ut))])):O.value?(l(),r("div",al,[e("p",ol,s(O.value),1),e("button",{class:"co-btn co-btn--secondary",onClick:ne},s(a.$t("common.retry")),1)])):V.value.length===0?(l(),r("div",ll,[e("div",nl,[(l(),$(w(g(fe)),{size:22}))]),e("h3",il,s(a.$t("settings.multiagent.empty")),1),e("p",dl,s(a.$t("settings.multiagent.emptyDesc")),1),e("div",rl,[e("button",{class:"co-btn co-btn--secondary",onClick:c[6]||(c[6]=i=>N.value=!0)},[(l(),$(w(g(Ge)),{size:14})),E(" "+s(a.$t("settings.multiagent.fromTemplate")),1)]),e("button",{class:"co-btn co-btn--primary",onClick:c[7]||(c[7]=i=>U.value=!0)},s(a.$t("settings.multiagent.newTeam")),1)])])):v.value.length>0?(l(),r("div",cl,[(l(!0),r(te,null,se(v.value,(i,M)=>(l(),r("div",{key:i.id,class:ee(["team-row",{"is-inactive":!i.is_active}]),onClick:R=>ke(i)},[e("span",ml,s(String(M+1).padStart(2,"0")),1),e("div",pl,[e("span",vl,s(i.name),1),e("span",gl,s(d[i.mode]),1),i.mode==="council"?(l(),r("span",_l,s(i.cross_review?a.$t("settings.multiagent.crossMode"):a.$t("settings.multiagent.independentMode")),1)):z("",!0),i.is_active?z("",!0):(l(),r("span",hl,s(a.$t("settings.multiagent.inactiveBadge")),1))]),e("span",fl,[(l(),$(w(g(fe)),{size:12})),E(" "+s(i.agents.length)+" "+s(a.$t("settings.multiagent.agentUnit")),1)]),e("div",yl,[e("button",{class:"icon-btn",title:a.$t("settings.multiagent.copyPayload"),onClick:Le(R=>ie(i),["stop"])},[(l(),$(w(g(kt)),{size:15}))],8,bl),e("button",{class:"icon-btn icon-btn--danger",title:a.$t("common.delete"),onClick:Le(R=>he(i),["stop"])},[(l(),$(w(g(Xe)),{size:15}))],8,$l)]),(l(),$(w(g(wt)),{size:15,class:"team-chevron"}))],10,ul))),128))])):(l(),r("div",kl,[(l(),$(w(g(je)),{size:22,class:"team-state-icon"})),e("p",wl,s(a.$t("settings.multiagent.noResults")),1),e("p",Cl,s(a.$t("settings.multiagent.noResultsDesc")),1),e("button",{class:"co-btn co-btn--secondary",onClick:_},s(a.$t("settings.multiagent.clearFilters")),1)])),q(g(ye),{"model-value":N.value,onClose:c[8]||(c[8]=i=>N.value=!1),size:"large"},{default:le(()=>[e("div",Ml,[e("h3",null,s(a.$t("settings.multiagent.templateTitle")),1),e("p",zl,s(a.$t("settings.multiagent.templateHint")),1),e("div",Sl,[(l(!0),r(te,null,se(g(No),i=>(l(),r("button",{key:i,class:ee(["category-btn",{active:I.value===i}]),onClick:M=>I.value=i},s(i==="全部"?a.$t("settings.multiagent.allCategories"):i),11,Tl))),128))]),e("div",Vl,[(l(!0),r(te,null,se(ae.value,i=>(l(),r("div",{key:i.id,class:"template-card",onClick:M=>D(i)},[e("div",Ul,[e("h4",null,s(i.name),1),e("span",Al,s(d[i.mode]),1)]),e("p",Ll,s(i.description),1),e("div",Pl,[e("span",Bl,[(l(),$(w(g(fe)),{size:14})),E(" "+s(a.$t("settings.multiagent.memberCount",{n:i.agents.length})),1)]),e("span",El,s(i.category),1)])],8,Dl))),128))])])]),_:1},8,["model-value"]),q(g(ye),{"model-value":U.value,title:a.$t("settings.multiagent.form.createTitle"),size:"medium",onClose:de},{footer:le(()=>[e("button",{class:"co-btn co-btn--secondary",onClick:de},s(a.$t("common.cancel")),1),e("button",{class:"co-btn co-btn--primary",disabled:!h.value.name.trim(),onClick:Me},s(a.$t("settings.multiagent.form.createAndAddMembers")),9,on)]),default:le(()=>[e("div",Nl,[e("div",Hl,[e("label",Ol,[E(s(a.$t("settings.multiagent.form.name"))+" ",1),c[15]||(c[15]=e("span",{class:"af-required"},"*",-1))]),B(e("input",{id:"team-form-name","onUpdate:modelValue":c[9]||(c[9]=i=>h.value.name=i),type:"text",class:"co-input",placeholder:a.$t("settings.multiagent.form.namePlaceholder")},null,8,Fl),[[Q,h.value.name]])]),e("div",Rl,[e("label",Gl,s(a.$t("settings.multiagent.form.description")),1),B(e("textarea",{id:"team-form-desc","onUpdate:modelValue":c[10]||(c[10]=i=>h.value.description=i),class:"co-textarea",rows:"3",placeholder:a.$t("settings.multiagent.form.descriptionPlaceholder")},null,8,jl),[[Q,h.value.description]])]),e("div",ql,[e("span",Il,[E(s(a.$t("settings.multiagent.form.mode"))+" ",1),c[16]||(c[16]=e("span",{class:"af-required"},"*",-1))]),e("div",Jl,[(l(),r(te,null,se(L,i=>e("label",{key:i.id,class:ee(["mode-option",{selected:h.value.mode===i.id}])},[B(e("input",{"onUpdate:modelValue":M=>h.value.mode=M,type:"radio",value:i.id,class:"mode-input"},null,8,Wl),[[Ct,h.value.mode]]),c[17]||(c[17]=e("span",{class:"mode-radio","aria-hidden":"true"},null,-1)),e("span",Kl,[e("strong",null,s(i.name),1),e("span",null,s(i.desc),1)])],2)),64))])]),e("div",Xl,[h.value.mode==="council"?(l(),r("div",Yl,[e("div",Ql,[e("span",Zl,s(a.$t("settings.multiagent.form.crossReview")),1),e("span",xl,s(a.$t("settings.multiagent.form.crossReviewHint")),1)]),q(pe,{modelValue:h.value.cross_review,"onUpdate:modelValue":c[11]||(c[11]=i=>h.value.cross_review=i),width:40,height:22,"aria-label":a.$t("settings.multiagent.form.crossReview")},null,8,["modelValue","aria-label"])])):z("",!0),e("div",en,[e("div",tn,[e("span",sn,s(a.$t("settings.multiagent.form.enableSkills")),1),e("span",an,s(a.$t("settings.multiagent.form.enableSkillsHint")),1)]),q(pe,{modelValue:h.value.enable_skills,"onUpdate:modelValue":c[12]||(c[12]=i=>h.value.enable_skills=i),width:40,height:22,"aria-label":a.$t("settings.multiagent.form.enableSkills")},null,8,["modelValue","aria-label"])])])])]),_:1},8,["model-value","title"])]),q(g(qt),{"model-value":!!k.value,size:"wide","show-header":!1,"mask-closable":!0,"onUpdate:modelValue":we},{default:le(()=>[k.value?(l(),$(Eo,{key:0,team:k.value,onBack:c[13]||(c[13]=i=>k.value=null),onUpdated:Ce},null,8,["team"])):z("",!0)]),_:1},8,["model-value"])]))}}),vn=$e(ln,[["__scopeId","data-v-469d2ad5"]]);export{vn as default};
