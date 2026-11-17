var et=Object.defineProperty;var Be=Object.getOwnPropertySymbols;var tt=Object.prototype.hasOwnProperty,st=Object.prototype.propertyIsEnumerable;var Le=(h,p,m)=>p in h?et(h,p,{enumerable:!0,configurable:!0,writable:!0,value:m}):h[p]=m,Pe=(h,p)=>{for(var m in p||(p={}))tt.call(p,m)&&Le(h,m,p[m]);if(Be)for(var m of Be(p))st.call(p,m)&&Le(h,m,p[m]);return h};var I=(h,p,m)=>new Promise((F,x)=>{var V=O=>{try{W(m.next(O))}catch(U){x(U)}},J=O=>{try{W(m.throw(O))}catch(U){x(U)}},W=O=>O.done?F(O.value):Promise.resolve(O.value).then(V,J);W((m=m.apply(h,p)).next())});import{b as be,F as Ae,at as ot,o,j as k,G,T as lt,H as ae,e as d,f as e,y as xe,n as ee,g as Te,h as L,t as l,k as w,l as g,X as He,i as z,au as at,c as Q,r as T,_ as ke,av as nt,aw as it,I as te,J as se,ax as rt,ay as dt,q as Ie,u as ut,v as Je,az as ct,a7 as Ne,aA as mt,a5 as We,aB as ye,a9 as Xe,af as he,aC as Oe,aD as pt,z as B,aE as Fe,A as Y,U as fe,aa as vt,aF as gt,aG as ft,ag as _t,aj as Re,aH as yt,aI as ht,ab as Ke,aJ as bt,aK as kt,aL as je,aM as qe,a8 as $t,aN as wt,aO as Ct}from"./index-C5nri7pQ.js";import{i as Ye,j as Ve,k as zt,l as Me,M as St,S as pe,m as Tt,n as Vt,o as Mt,b as Qe}from"./agentTeams-0AfyIFCm.js";import{M as Ut,L as Dt}from"./useKeyboard-DUwCArMB.js";import{u as At}from"./useModelCatalog-0vn8DLOi.js";import{r as xt,a as Et,f as Bt,b as Lt}from"./providerRuntime-Bim9Xk0P.js";import"./countbot-logo-CNglRKg-.js";const Pt=["aria-labelledby"],Nt={key:0,class:"drawer-header"},Ot=["id"],Ft=["aria-label"],Rt={class:"drawer-body"},jt={key:1,class:"drawer-footer"},qt=be({__name:"Drawer",props:{modelValue:{type:Boolean},title:{default:""},size:{default:"medium"},placement:{default:"right"},closable:{type:Boolean,default:!0},maskClosable:{type:Boolean,default:!1},showHeader:{type:Boolean,default:!0}},emits:["update:modelValue","close"],setup(h,{emit:p}){const m=h,F=p,x=Q(()=>`drawer-title-${Math.random().toString(36).slice(2,9)}`),V=T(),J=()=>{F("update:modelValue",!1),F("close")},W=()=>{m.maskClosable&&J()},O=U=>{U.key==="Escape"&&m.modelValue&&m.closable&&J()};return Ae(()=>m.modelValue,U=>{document.body.style.overflow=U?"hidden":"",U?(document.addEventListener("keydown",O),setTimeout(()=>{var $;const P=($=V.value)==null?void 0:$.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');P==null||P.focus()},60)):document.removeEventListener("keydown",O)},{immediate:!0}),ot(()=>{document.removeEventListener("keydown",O),document.body.style.overflow=""}),(U,P)=>(o(),k(at,{to:"body"},[G(lt,{name:"drawer"},{default:ae(()=>[h.modelValue?(o(),d("div",{key:0,class:"drawer-overlay",onClick:W},[e("aside",{ref_key:"panelRef",ref:V,class:ee(["drawer-panel",[`drawer-${h.size}`,`drawer-${h.placement}`]]),role:"dialog","aria-modal":"true","aria-labelledby":x.value,onClick:P[0]||(P[0]=xe(()=>{},["stop"]))},[h.showHeader?(o(),d("header",Nt,[e("h2",{id:x.value,class:"drawer-title"},[Te(U.$slots,"title",{},()=>[L(l(h.title),1)],!0)],8,Ot),h.closable?(o(),d("button",{key:0,type:"button",class:"drawer-close","aria-label":U.$t("common.close"),onClick:J},[(o(),k(w(g(He)),{size:18}))],8,Ft)):z("",!0)])):z("",!0),e("div",Rt,[Te(U.$slots,"default",{},void 0,!0)]),U.$slots.footer?(o(),d("footer",jt,[Te(U.$slots,"footer",{},void 0,!0)])):z("",!0)],10,Pt)])):z("",!0)]),_:3})]))}}),Gt=ke(qt,[["__scopeId","data-v-b1db600d"]]),Ht={class:"dependency-graph"},It={class:"graph-header"},Jt={class:"graph-controls"},Wt=["title"],Xt=["title"],Kt={id:"arrowhead",markerWidth:"10",markerHeight:"10",refX:"9",refY:"3",orient:"auto"},Yt=["fill"],Qt={class:"edges"},Zt=["x1","y1","x2","y2","marker-end"],es={class:"nodes"},ts=["transform","onClick","onMouseenter"],ss=["x","y"],os={class:"node-label","text-anchor":"middle",dy:"0.3em"},ls=["y"],as={class:"tooltip-content"},ns={key:0},is={key:1,class:"tooltip-deps"},rs={class:"tooltip-label"},ds={key:0,class:"cycle-warning"},Ue=140,me=60,De=200,us=120,cs=be({__name:"DependencyGraph",props:{agents:{}},setup(h){const p=h,m=T(),F=T(),x=T(null),V=T(null),J=Q(()=>typeof window!="undefined"&&m.value&&getComputedStyle(m.value).getPropertyValue("--text-tertiary").trim()||"var(--text-tertiary)"),W=()=>{const v=new Map,f=new Set,M=_=>{if(f.has(_))return v.get(_)||0;f.add(_);const r=p.agents.find(E=>E.id===_);if(!r||!r.depends_on||r.depends_on.length===0)return v.set(_,0),0;const q=Math.max(...r.depends_on.map(E=>M(E)))+1;return v.set(_,q),q};return p.agents.forEach(_=>M(_.id)),v},O=()=>{const v=[],f=new Set,M=new Set,_=[],r=A=>{f.add(A),M.add(A),_.push(A);const q=p.agents.find(E=>E.id===A);if(q!=null&&q.depends_on){for(const E of q.depends_on)if(f.has(E)){if(M.has(E)){const b=_.indexOf(E);return v.push(_.slice(b)),!0}}else if(r(E))return!0}return _.pop(),M.delete(A),!1};return p.agents.forEach(A=>{f.has(A.id)||r(A.id)}),v},U=Q(()=>O()),P=Q(()=>{const v=W(),f=new Map,M=p.agents.map(r=>({id:r.id,label:r.role||r.id,task:r.task,depends_on:r.depends_on||[],hasCondition:!!r.condition,x:0,y:0,level:v.get(r.id)||0}));M.forEach(r=>{const A=r.level;f.has(A)||f.set(A,[]),f.get(A).push(r)});const _=800;return f.forEach((r,A)=>{const q=r.length*De,E=(_-q)/2+De/2,b=80+A*us;r.forEach((c,ne)=>{c.x=E+ne*De,c.y=b})}),M}),$=Q(()=>{const v=[];return P.value.forEach(f=>{f.depends_on.forEach(M=>{const _=P.value.find(r=>r.id===M);_&&v.push({from:M,to:f.id,x1:_.x,y1:_.y+me/2,x2:f.x,y2:f.y-me/2})})}),v}),le=v=>{x.value=x.value===v?null:v},X=v=>{if(!x.value)return!1;const f=P.value.find(M=>M.id===x.value);return f?v.from===x.value||v.to===x.value||f.depends_on.includes(v.from)||P.value.some(M=>M.depends_on.includes(x.value)&&M.id===v.to):!1},N=v=>P.value.find(f=>f.id===v),D=v=>{const f=N(v);return f?{left:`${f.x+Ue/2+10}px`,top:`${f.y-me/2}px`}:{}},H=()=>{x.value=null},oe=()=>{x.value=null};return(v,f)=>{var M,_,r,A,q,E;return o(),d("div",Ht,[e("div",It,[e("h3",null,l(v.$t("teams.dependency.title")),1),e("div",Jt,[e("button",{class:"control-btn",onClick:H,title:v.$t("teams.dependency.resetView")},[(o(),k(w(g(nt)),{size:16}))],8,Wt),e("button",{class:"control-btn",onClick:oe,title:v.$t("teams.dependency.autoLayout")},[(o(),k(w(g(it)),{size:16}))],8,Xt)])]),e("div",{ref_key:"graphContainer",ref:m,class:"graph-container"},[(o(),d("svg",{ref_key:"svgElement",ref:F,class:"graph-svg"},[e("defs",null,[e("marker",Kt,[e("polygon",{points:"0 0, 10 3, 0 6",fill:J.value},null,8,Yt)]),f[1]||(f[1]=e("marker",{id:"arrowhead-highlighted",markerWidth:"10",markerHeight:"10",refX:"9",refY:"3",orient:"auto"},[e("polygon",{points:"0 0, 10 3, 0 6",fill:"var(--color-accent)"})],-1))]),e("g",Qt,[(o(!0),d(te,null,se($.value,b=>(o(),d("line",{key:`${b.from}-${b.to}`,x1:b.x1,y1:b.y1,x2:b.x2,y2:b.y2,class:ee(["edge",{highlighted:X(b)}]),"marker-end":X(b)?"url(#arrowhead-highlighted)":"url(#arrowhead)"},null,10,Zt))),128))]),e("g",es,[(o(!0),d(te,null,se(P.value,b=>(o(),d("g",{key:b.id,transform:`translate(${b.x}, ${b.y})`,class:ee(["node",{highlighted:x.value===b.id,"has-condition":b.hasCondition}]),onClick:c=>le(b.id),onMouseenter:c=>V.value=b.id,onMouseleave:f[0]||(f[0]=c=>V.value=null)},[e("rect",{width:Ue,height:me,x:-Ue/2,y:-me/2,rx:"8",class:"node-rect"},null,8,ss),e("text",os,l(b.label),1),b.hasCondition?(o(),d("text",{key:0,class:"condition-indicator","text-anchor":"middle",y:me/2-8,"font-size":"10"},l(v.$t("teams.dependency.conditional")),9,ls)):z("",!0)],42,ts))),128))])],512)),V.value?(o(),d("div",{key:0,class:"node-tooltip",style:rt(D(V.value))},[e("div",as,[e("strong",null,l((M=N(V.value))==null?void 0:M.label),1),(_=N(V.value))!=null&&_.task?(o(),d("p",ns,l((r=N(V.value))==null?void 0:r.task),1)):z("",!0),(q=(A=N(V.value))==null?void 0:A.depends_on)!=null&&q.length?(o(),d("div",is,[e("span",rs,l(v.$t("teams.dependency.depends")),1),L(" "+l((E=N(V.value))==null?void 0:E.depends_on.join(", ")),1)])):z("",!0)])],4)):z("",!0)],512),U.value.length>0?(o(),d("div",ds,[(o(),k(w(g(dt)),{size:16})),e("div",null,[e("strong",null,l(v.$t("teams.dependency.cycleDetected")),1),(o(!0),d(te,null,se(U.value,(b,c)=>(o(),d("p",{key:c},l(b.join(" → "))+" → "+l(b[0]),1))),128))])])):z("",!0)])}}}),ms=ke(cs,[["__scopeId","data-v-38c6926c"]]),ps={class:"team-detail"},vs={class:"detail-header"},gs={class:"team-info-section"},fs={class:"team-title-row"},_s={class:"team-badges"},ys={class:"badge badge-mode"},hs={key:0,class:"team-description"},bs={class:"members-section"},ks={class:"section-header"},$s={class:"section-actions"},ws={key:0,class:"graph-section"},Cs={key:1,class:"empty-members"},zs={key:2,class:"members-list"},Ss={class:"member-header"},Ts={class:"member-info"},Vs={class:"member-number"},Ms={class:"member-actions"},Us=["onClick"],Ds=["onClick"],As={class:"member-details"},xs={class:"detail-item"},Es={class:"detail-value"},Bs={key:0,class:"detail-item"},Ls={class:"detail-value"},Ps={key:1,class:"detail-item"},Ns={class:"detail-value"},Os={key:2,class:"detail-item"},Fs={class:"detail-value"},Rs={key:3,class:"detail-item full-width"},js={class:"condition-badge"},qs={class:"condition-type"},Gs={class:"condition-node"},Hs={class:"condition-text"},Is={key:4,class:"detail-item full-width"},Js={class:"prompt-preview"},Ws={class:"dialog-content"},Xs={class:"tabs-nav"},Ks={class:"tabs-content"},Ys={class:"tab-panel"},Qs={class:"form-group"},Zs={class:"form-group"},eo={class:"form-group"},to={key:0,class:"form-group"},so={class:"toggle-wrapper"},oo={class:"form-group"},lo={class:"toggle-wrapper"},ao={key:0,class:"tab-panel"},no={class:"toggle-header"},io={class:"toggle-label"},ro={key:0,class:"config-badge"},uo={key:0,class:"model-config-section"},co={class:"form-grid"},mo={class:"form-group"},po={class:"form-group"},vo={class:"advanced-config"},go={class:"advanced-content"},fo={class:"form-group"},_o=["placeholder"],yo={class:"form-hint"},ho={class:"form-group"},bo=["placeholder"],ko={class:"form-hint"},$o={class:"form-group"},wo=["disabled"],Co={key:1,class:"empty-state-inline"},zo={class:"dialog-content"},So={class:"form-group"},To={key:0,class:"form-group"},Vo={key:1,class:"form-group"},Mo={key:2,class:"form-group"},Uo={key:3,class:"form-group"},Do={class:"dependency-selector"},Ao={key:0,class:"selected-tags"},xo=["onClick"],Eo=["disabled"],Bo={value:""},Lo=["value"],Po={key:4,class:"form-group"},No={key:0,class:"condition-disabled-hint"},Oo={key:1,class:"condition-config"},Fo={class:"toggle-wrapper"},Ro={key:0,class:"condition-form"},jo={class:"form-row"},qo={class:"form-col"},Go={class:"form-col"},Ho=["value"],Io={class:"form-row"},Jo={class:"form-col full"},Wo={class:"form-hint"},Xo={class:"form-group"},Ko=["disabled"],Yo=be({__name:"TeamDetail",props:{team:{}},emits:["back","updated"],setup(h,{emit:p}){const m=h,F=p,{t:x}=Ie(),V=Ye(),J=ut(),W=Qe(),O=At(),{confirm:U}=Ke(),P={pipeline:"流水线",graph:"依赖图",council:"多视角"},$=T([]),le=T(!1),X=T(!1),N=T("basic"),D=T({name:"",description:"",mode:"council",cross_review:!0,enable_skills:!1}),H=T(!1),oe=T(!1),v=T(null),f=T([]),M=T(!1),_=()=>Me(),r=T(_()),A=T(_()),q=Q(()=>f.value.map(n=>({value:n.id,label:n.name}))),E=T(!1),b=T(null),c=T({id:"",role:"",perspective:"",task:"",system_prompt:"",depends_on_str:"",enable_condition:!1,condition_type:"output_contains",condition_node:"",condition_text:""}),ne=Q(()=>c.value.id.trim()?m.team.mode==="council"?!!c.value.perspective.trim():!!c.value.role.trim():!1);Ae(()=>m.team,n=>{n&&($.value=JSON.parse(JSON.stringify(n.agents||[])),D.value={name:n.name,description:n.description||"",mode:n.mode,cross_review:n.cross_review,enable_skills:n.enable_skills||!1})},{immediate:!0}),Je(()=>I(this,null,function*(){yield R(),yield ve()}));const $e=()=>{b.value=null,c.value={id:`agent${$.value.length+1}`,role:"",perspective:"",task:"",system_prompt:"",depends_on_str:"",enable_condition:!1,condition_type:"output_contains",condition_node:"",condition_text:""},E.value=!0},we=n=>{var y,j,K;b.value=n;const t=$.value[n],a=!!t.condition;c.value={id:t.id,role:t.role||"",perspective:t.perspective||"",task:t.task||"",system_prompt:t.system_prompt||"",depends_on_str:(t.depends_on||[]).join(", "),enable_condition:a,condition_type:((y=t.condition)==null?void 0:y.type)||"output_contains",condition_node:((j=t.condition)==null?void 0:j.node)||"",condition_text:((K=t.condition)==null?void 0:K.text)||""},E.value=!0},Ce=()=>{const n=new Set,t=[];for(c.value.depends_on_str.split(",").map(y=>y.trim()).filter(Boolean).forEach(y=>{n.add(y),t.push(y)});t.length>0;){const y=t.shift(),j=$.value.find(K=>K.id===y);j!=null&&j.depends_on&&j.depends_on.forEach(K=>{n.has(K)||(n.add(K),t.push(K))})}return Array.from(n)},_e=n=>$.value.find(t=>t.id===n),ie=()=>c.value.depends_on_str.split(",").map(n=>n.trim()).filter(Boolean),re=()=>{const n=c.value.id.trim(),t=ie();return $.value.filter(a=>{if(b.value!==null){const y=$.value[b.value];if(a.id===(y==null?void 0:y.id))return!1}return a.id===n?!1:!t.includes(a.id)})},ze=n=>{const t=n.target,a=t.value;if(!a)return;const y=ie();y.push(a),c.value.depends_on_str=y.join(", "),t.value=""},s=n=>{const a=ie().filter(y=>y!==n);c.value.depends_on_str=a.join(", "),a.length===0&&(c.value.enable_condition=!1,c.value.condition_node="",c.value.condition_text="")},u=n=>I(this,null,function*(){(yield U({title:"确认删除",message:"确定要删除这个成员吗？",type:"danger",confirmText:"删除",confirmVariant:"danger"}))&&($.value.splice(n,1),Ee())}),i=()=>{E.value=!1,b.value=null},C=()=>{const n={id:c.value.id.trim()};if(m.team.mode==="council"){n.perspective=c.value.perspective.trim();const t=n.perspective.split(/[，,]/);n.role=t[0].trim()||n.id}else n.role=c.value.role.trim(),n.task=c.value.task.trim();c.value.system_prompt.trim()&&(n.system_prompt=c.value.system_prompt.trim()),m.team.mode==="graph"?(n.depends_on=c.value.depends_on_str.split(",").map(t=>t.trim()).filter(Boolean),c.value.enable_condition&&c.value.condition_node&&c.value.condition_text.trim()&&(n.condition={type:c.value.condition_type,node:c.value.condition_node,text:c.value.condition_text.trim()})):n.depends_on=[],b.value!==null?$.value[b.value]=n:$.value.push(n),i(),Ee()};function R(){return I(this,null,function*(){try{const n=yield O.listProviders();f.value=n.map(t=>({id:t.id,name:t.name,defaultApiBase:Et(t),defaultModel:xt(t)})),ge()}catch(n){}})}function ve(){return I(this,null,function*(){if(!(!m.team.id||!J.isAdmin))try{const n=yield Ve.getConfig(m.team.id);A.value=zt(void 0,n.global_defaults),n.use_custom_model?de(n.model_settings,!0):de(n.global_defaults,!1)}catch(n){}})}function de(n,t){M.value=!0;try{H.value=t,r.value=Me(A.value,t?n:void 0),v.value=null,ge()}finally{M.value=!1}}function ge(){if(f.value.length===0||Bt(f.value,r.value.provider))return;const a=Lt(f.value)||f.value[0];a&&(r.value.provider=a.id,r.value.api_base||(r.value.api_base=a.defaultApiBase||""),(!r.value.model||r.value.model===St.model)&&(r.value.model=a.defaultModel||r.value.model))}function Se(){if(!H.value){v.value=null;return}r.value=Me(A.value,r.value),v.value=null}function Z(){return I(this,null,function*(){var n,t;oe.value=!0,v.value=null;try{const a=yield O.testConnection(Pe({provider:r.value.provider||"zhipu",api_key:r.value.api_key||void 0,api_base:r.value.api_base||void 0,model:r.value.model||"glm-5"},Vt(r.value)));v.value={success:a.success,message:a.success?a.message||x("settings.providers.testSuccess"):a.error||a.message||x("settings.providers.testFailed")}}catch(a){v.value={success:!1,message:((t=(n=a.response)==null?void 0:n.data)==null?void 0:t.error)||a.message||x("settings.providers.testFailed")}}finally{oe.value=!1}})}Ae(()=>r.value.provider,(n,t)=>{if(!n||f.value.length===0||M.value)return;const a=f.value.find(ce=>ce.id===n),y=t?f.value.find(ce=>ce.id===t):null;if(!a)return;(!r.value.api_base||!!(y!=null&&y.defaultApiBase)&&r.value.api_base===y.defaultApiBase)&&(r.value.api_base=a.defaultApiBase||""),(!r.value.model||!!(y!=null&&y.defaultModel)&&r.value.model===y.defaultModel)&&a.defaultModel&&(r.value.model=a.defaultModel)});const ue=()=>{X.value=!1,N.value="basic"},Ze=()=>I(this,null,function*(){try{yield V.updateTeam(m.team.id,{name:D.value.name,description:D.value.description,mode:D.value.mode,cross_review:D.value.cross_review,enable_skills:D.value.enable_skills,agents:$.value,is_active:m.team.is_active}),J.isAdmin&&(H.value?yield Ve.updateConfig(m.team.id,Mt(r.value,A.value)):m.team.use_custom_model&&(yield Ve.resetConfig(m.team.id))),W.success("团队信息已更新"),ue(),F("updated")}catch(n){W.error(n.message||"保存失败")}}),Ee=()=>I(this,null,function*(){try{yield V.updateTeam(m.team.id,{name:m.team.name,description:m.team.description,mode:m.team.mode,cross_review:m.team.cross_review,enable_skills:m.team.enable_skills||!1,agents:$.value,is_active:m.team.is_active}),W.success("成员已更新"),F("updated")}catch(n){W.error(n.message||"保存失败")}});return(n,t)=>(o(),d("div",ps,[e("div",vs,[e("button",{class:"btn-back",onClick:t[0]||(t[0]=a=>n.$emit("back"))},[(o(),k(w(g(ct)),{size:16})),t[30]||(t[30]=L(" 返回团队列表 ",-1))]),e("div",gs,[e("div",fs,[e("h2",null,l(h.team.name),1),e("div",_s,[e("span",ys,l(P[h.team.mode]),1),h.team.mode==="council"?(o(),d("span",{key:0,class:ee(["badge badge-review",h.team.cross_review?"badge-cross":"badge-independent"])},l(h.team.cross_review?"交叉模式":"独立模式"),3)):z("",!0)]),e("button",{class:"icon-btn",onClick:t[1]||(t[1]=a=>X.value=!0)},[(o(),k(w(g(Ne)),{size:16}))])]),h.team.description?(o(),d("p",hs,l(h.team.description),1)):z("",!0)])]),e("div",bs,[e("div",ks,[e("h3",null,"团队成员 ("+l($.value.length)+")",1),e("div",$s,[h.team.mode==="graph"&&$.value.length>0?(o(),d("button",{key:0,class:"btn-secondary",onClick:t[2]||(t[2]=a=>le.value=!le.value)},[(o(),k(w(g(mt)),{size:16})),L(" "+l(le.value?"隐藏依赖图":"查看依赖图"),1)])):z("",!0),e("button",{class:"btn-primary",onClick:$e},[(o(),k(w(g(We)),{size:16})),t[31]||(t[31]=L(" 添加成员 ",-1))])])]),h.team.mode==="graph"&&le.value&&$.value.length>0?(o(),d("div",ws,[G(ms,{agents:$.value},null,8,["agents"])])):z("",!0),$.value.length===0?(o(),d("div",Cs,[(o(),k(w(g(ye)),{size:48,class:"empty-icon"})),t[32]||(t[32]=e("p",null,"暂无成员，点击上方按钮添加",-1))])):(o(),d("div",zs,[(o(!0),d(te,null,se($.value,(a,y)=>{var j;return o(),d("div",{key:y,class:"member-card"},[e("div",Ss,[e("div",Ts,[e("span",Vs,"#"+l(y+1),1),e("h4",null,l(a.role||a.perspective||a.id),1)]),e("div",Ms,[e("button",{class:"icon-btn",onClick:K=>we(y)},[(o(),k(w(g(Ne)),{size:16}))],8,Us),e("button",{class:"icon-btn danger",onClick:K=>u(y)},[(o(),k(w(g(Xe)),{size:16}))],8,Ds)])]),e("div",As,[e("div",xs,[t[33]||(t[33]=e("span",{class:"detail-label"},"ID:",-1)),e("span",Es,l(a.id),1)]),h.team.mode==="council"?(o(),d("div",Bs,[t[34]||(t[34]=e("span",{class:"detail-label"},"视角:",-1)),e("span",Ls,l(a.perspective||"-"),1)])):(o(),d("div",Ps,[t[35]||(t[35]=e("span",{class:"detail-label"},"任务:",-1)),e("span",Ns,l(a.task||"-"),1)])),h.team.mode==="graph"&&((j=a.depends_on)!=null&&j.length)?(o(),d("div",Os,[t[36]||(t[36]=e("span",{class:"detail-label"},"依赖:",-1)),e("span",Fs,l(a.depends_on.join(", ")),1)])):z("",!0),a.condition?(o(),d("div",Rs,[t[37]||(t[37]=e("span",{class:"detail-label"},"执行条件:",-1)),e("div",js,[e("span",qs,l(a.condition.type==="output_contains"?"包含":"不包含"),1),e("span",Gs,l(a.condition.node),1),e("span",Hs,'"'+l(a.condition.text)+'"',1)])])):z("",!0),a.system_prompt?(o(),d("div",Is,[t[38]||(t[38]=e("span",{class:"detail-label"},"系统提示词:",-1)),e("div",Js,l(a.system_prompt),1)])):z("",!0)])])}),128))]))]),G(g(he),{"model-value":X.value,title:"编辑团队信息",size:"large",onClose:ue},{footer:ae(()=>[e("button",{class:"co-btn co-btn--secondary",onClick:ue},"取消"),e("button",{class:"co-btn co-btn--primary",onClick:Ze},"保存")]),default:ae(()=>{var a,y,j,K,ce;return[e("div",Ws,[e("div",Xs,[e("button",{class:ee(["tab-btn",{active:N.value==="basic"}]),onClick:t[3]||(t[3]=S=>N.value="basic")},[(o(),k(w(g(Oe)),{size:16})),t[39]||(t[39]=e("span",null,"基本信息",-1))],2),g(J).isAdmin?(o(),d("button",{key:0,class:ee(["tab-btn",{active:N.value==="model"}]),onClick:t[4]||(t[4]=S=>N.value="model")},[(o(),k(w(g(pt)),{size:16})),t[40]||(t[40]=e("span",null,"模型配置",-1))],2)):z("",!0)]),e("div",Ks,[B(e("div",Ys,[e("div",Qs,[t[41]||(t[41]=e("label",null,[L("团队名称 "),e("span",{class:"required"},"*")],-1)),B(e("input",{"onUpdate:modelValue":t[5]||(t[5]=S=>D.value.name=S),type:"text",class:"form-input"},null,512),[[Y,D.value.name]])]),e("div",Zs,[t[42]||(t[42]=e("label",null,"团队描述",-1)),B(e("textarea",{"onUpdate:modelValue":t[6]||(t[6]=S=>D.value.description=S),class:"form-textarea",rows:"3"},null,512),[[Y,D.value.description]])]),e("div",eo,[t[44]||(t[44]=e("label",null,[L("协作模式 "),e("span",{class:"required"},"*")],-1)),B(e("select",{"onUpdate:modelValue":t[7]||(t[7]=S=>D.value.mode=S),class:"form-select"},[...t[43]||(t[43]=[e("option",{value:"pipeline"},"流水线 (Pipeline)",-1),e("option",{value:"graph"},"依赖图 (Graph)",-1),e("option",{value:"council"},"多视角 (Council)",-1)])],512),[[fe,D.value.mode]])]),D.value.mode==="council"?(o(),d("div",to,[e("div",so,[t[45]||(t[45]=e("div",{class:"toggle-content"},[e("span",{class:"toggle-title"},"启用交叉评审"),e("p",{class:"toggle-hint"},"关闭后，成员将独立分析，不互相评审")],-1)),G(pe,{modelValue:D.value.cross_review,"onUpdate:modelValue":t[8]||(t[8]=S=>D.value.cross_review=S),width:44,height:24,"aria-label":"启用交叉评审"},null,8,["modelValue"])])])):z("",!0),e("div",oo,[e("div",lo,[t[46]||(t[46]=e("div",{class:"toggle-content"},[e("span",{class:"toggle-title"},"启用技能系统"),e("p",{class:"toggle-hint"},"开启后，子 Agent 可以使用技能（如图片生成、天气查询等）")],-1)),G(pe,{modelValue:D.value.enable_skills,"onUpdate:modelValue":t[9]||(t[9]=S=>D.value.enable_skills=S),width:44,height:24,"aria-label":"启用技能系统"},null,8,["modelValue"])])])],512),[[Fe,N.value==="basic"]]),g(J).isAdmin?B((o(),d("div",ao,[e("div",{class:ee(["config-toggle",{active:H.value}])},[e("div",no,[e("label",io,[G(pe,{modelValue:H.value,"onUpdate:modelValue":t[10]||(t[10]=S=>H.value=S),width:48,height:28,"aria-label":"为此团队使用自定义模型",onChange:Se},null,8,["modelValue"]),t[47]||(t[47]=e("div",{class:"toggle-content-large"},[e("span",{class:"toggle-text"},"为此团队使用自定义模型"),e("span",{class:"toggle-hint"},"团队成员将使用此配置的模型和 API")],-1))]),H.value?(o(),d("div",ro,[(o(),k(w(g(vt)),{size:14})),t[48]||(t[48]=e("span",null,"自定义",-1))])):z("",!0)])],2),H.value?(o(),d("div",uo,[t[49]||(t[49]=e("div",{class:"model-config-toolbar"},[e("div",{class:"model-config-copy"},[e("h4",null,"模型设置")])],-1)),e("div",co,[e("div",mo,[e("label",null,l(n.$t("settings.providers.selectProvider")),1),G(Tt,{modelValue:r.value.provider,"onUpdate:modelValue":t[11]||(t[11]=S=>r.value.provider=S),options:q.value,placeholder:n.$t("settings.providers.selectProvider"),searchable:""},null,8,["modelValue","options","placeholder"])]),e("div",po,[e("label",null,l(n.$t("settings.providers.model")),1),B(e("input",{"onUpdate:modelValue":t[12]||(t[12]=S=>r.value.model=S),type:"text",class:"form-input",placeholder:"glm-5"},null,512),[[Y,r.value.model]])])]),G(Ut,{temperature:(a=r.value.temperature)!=null?a:0,"max-tokens":(y=r.value.max_tokens)!=null?y:0,"max-iterations":(j=r.value.max_iterations)!=null?j:0,"thinking-enabled":(K=r.value.thinking_enabled)!=null?K:!0,"stream-enabled":(ce=r.value.stream_enabled)!=null?ce:!0,"onUpdate:temperature":t[13]||(t[13]=S=>r.value.temperature=S),"onUpdate:maxTokens":t[14]||(t[14]=S=>r.value.max_tokens=S),"onUpdate:maxIterations":t[15]||(t[15]=S=>r.value.max_iterations=S),"onUpdate:thinkingEnabled":t[16]||(t[16]=S=>r.value.thinking_enabled=S),"onUpdate:streamEnabled":t[17]||(t[17]=S=>r.value.stream_enabled=S)},null,8,["temperature","max-tokens","max-iterations","thinking-enabled","stream-enabled"]),e("details",vo,[e("summary",null,[(o(),k(w(g(gt)),{size:16})),e("span",null,l(n.$t("chat.sessionConfig.advancedApiSettings")),1),(o(),k(w(g(ft)),{size:16,class:"chevron"}))]),e("div",go,[e("div",fo,[e("label",null,l(n.$t("settings.providers.apiKey")),1),B(e("input",{"onUpdate:modelValue":t[18]||(t[18]=S=>r.value.api_key=S),type:"password",placeholder:n.$t("chat.sessionConfig.leaveEmptyForGlobal"),class:"form-input"},null,8,_o),[[Y,r.value.api_key]]),e("p",yo,l(n.$t("chat.sessionConfig.apiKeyHint")),1)]),e("div",ho,[e("label",null,l(n.$t("settings.providers.baseUrl")),1),B(e("input",{"onUpdate:modelValue":t[19]||(t[19]=S=>r.value.api_base=S),type:"text",placeholder:n.$t("chat.sessionConfig.leaveEmptyForGlobal"),class:"form-input"},null,8,bo),[[Y,r.value.api_base]]),e("p",ko,l(n.$t("chat.sessionConfig.apiBaseHint")),1)]),e("div",$o,[e("button",{onClick:Z,class:"btn-secondary",disabled:oe.value},[(o(),k(w(oe.value?g(_t):g(Re)),{size:16,class:ee({spin:oe.value})},null,8,["class"])),e("span",null,l(oe.value?n.$t("settings.providers.testing"):n.$t("settings.providers.testConnection")),1)],8,wo)]),v.value?(o(),d("div",{key:0,class:ee(["test-result",v.value.success?"success":"error"])},[(o(),k(w(v.value.success?g(Re):g(yt)),{size:16})),e("span",null,l(v.value.message),1)],2)):z("",!0)])])])):(o(),d("div",Co,[(o(),k(w(g(ht)),{size:32,class:"empty-icon"})),t[50]||(t[50]=e("div",{class:"empty-text"},[e("h4",null,"使用全局默认配置"),e("p",null,"启用自定义配置以为此团队设置专属的模型和 API")],-1))]))],512)),[[Fe,N.value==="model"]]):z("",!0)])])]}),_:1},8,["model-value"]),G(g(he),{"model-value":E.value,title:b.value===null?"添加成员":"编辑成员",size:"large",onClose:i},{footer:ae(()=>[e("button",{class:"co-btn co-btn--secondary",onClick:i},"取消"),e("button",{class:"co-btn co-btn--primary",onClick:C,disabled:!ne.value},"保存",8,Ko)]),default:ae(()=>[e("div",zo,[e("div",So,[t[51]||(t[51]=e("label",null,[L("成员 ID "),e("span",{class:"required"},"*")],-1)),B(e("input",{"onUpdate:modelValue":t[20]||(t[20]=a=>c.value.id=a),type:"text",class:"form-input",placeholder:"例如：analyst"},null,512),[[Y,c.value.id]]),t[52]||(t[52]=e("p",{class:"form-hint"},"唯一标识符，用于依赖关系引用",-1))]),h.team.mode==="council"?(o(),d("div",To,[t[53]||(t[53]=e("label",null,[L("视角 (Perspective) "),e("span",{class:"required"},"*")],-1)),B(e("input",{"onUpdate:modelValue":t[21]||(t[21]=a=>c.value.perspective=a),type:"text",class:"form-input",placeholder:"例如：技术架构师，关注可扩展性"},null,512),[[Y,c.value.perspective]]),t[54]||(t[54]=e("p",{class:"form-hint"},"描述这个成员的分析视角",-1))])):(o(),d("div",Vo,[t[55]||(t[55]=e("label",null,[L("角色 (Role) "),e("span",{class:"required"},"*")],-1)),B(e("input",{"onUpdate:modelValue":t[22]||(t[22]=a=>c.value.role=a),type:"text",class:"form-input",placeholder:"例如：需求分析师"},null,512),[[Y,c.value.role]])])),h.team.mode!=="council"?(o(),d("div",Mo,[t[56]||(t[56]=e("label",null,"任务 (Task)",-1)),B(e("textarea",{"onUpdate:modelValue":t[23]||(t[23]=a=>c.value.task=a),class:"form-textarea",rows:"3",placeholder:"描述这个成员的具体任务..."},null,512),[[Y,c.value.task]]),t[57]||(t[57]=e("p",{class:"form-hint"},"`task` 会作为实际执行任务传给子 Agent；如果未填写系统提示词，系统也会基于角色和任务自动生成默认系统提示。",-1))])):z("",!0),h.team.mode==="graph"?(o(),d("div",Uo,[t[58]||(t[58]=e("label",null,"依赖 (Depends On)",-1)),e("div",Do,[ie().length>0?(o(),d("div",Ao,[(o(!0),d(te,null,se(ie(),a=>(o(),d("span",{key:a,class:"dependency-tag"},[L(l(a)+" ",1),e("button",{type:"button",class:"tag-remove",onClick:y=>s(a)},"×",8,xo)]))),128))])):z("",!0),e("select",{class:"form-select",onChange:t[24]||(t[24]=a=>ze(a)),disabled:re().length===0},[e("option",Bo,l(re().length===0?"没有可选的依赖节点":"选择依赖节点..."),1),(o(!0),d(te,null,se(re(),a=>(o(),d("option",{key:a.id,value:a.id},l(a.id)+" - "+l(a.role||a.perspective||"未命名"),9,Lo))),128))],40,Eo)]),t[59]||(t[59]=e("p",{class:"form-hint"},"选择此成员需要等待哪些成员完成后才能执行",-1))])):z("",!0),h.team.mode==="graph"?(o(),d("div",Po,[t[68]||(t[68]=e("label",null,"执行条件（可选）",-1)),c.value.depends_on_str.trim()?(o(),d("div",Oo,[e("div",Fo,[t[61]||(t[61]=e("div",{class:"toggle-content"},[e("span",{class:"toggle-title"},"启用条件执行"),e("p",{class:"toggle-hint"},"根据依赖节点的输出决定是否执行此节点")],-1)),G(pe,{modelValue:c.value.enable_condition,"onUpdate:modelValue":t[25]||(t[25]=a=>c.value.enable_condition=a),width:44,height:24,"aria-label":"启用条件执行"},null,8,["modelValue"])]),c.value.enable_condition?(o(),d("div",Ro,[e("div",jo,[e("div",qo,[t[63]||(t[63]=e("label",null,"条件类型",-1)),B(e("select",{"onUpdate:modelValue":t[26]||(t[26]=a=>c.value.condition_type=a),class:"form-select"},[...t[62]||(t[62]=[e("option",{value:"output_contains"},"输出包含",-1),e("option",{value:"output_not_contains"},"输出不包含",-1)])],512),[[fe,c.value.condition_type]])]),e("div",Go,[t[65]||(t[65]=e("label",null,"检查节点",-1)),B(e("select",{"onUpdate:modelValue":t[27]||(t[27]=a=>c.value.condition_node=a),class:"form-select"},[t[64]||(t[64]=e("option",{value:""},"选择节点...",-1)),(o(!0),d(te,null,se(Ce(),a=>{var y,j;return o(),d("option",{key:a,value:a},l(a)+" - "+l(((y=_e(a))==null?void 0:y.role)||((j=_e(a))==null?void 0:j.perspective)||"未命名"),9,Ho)}),128))],512),[[fe,c.value.condition_node]]),t[66]||(t[66]=e("p",{class:"form-hint"},"可以选择任何上游节点（包括间接依赖）",-1))])]),e("div",Io,[e("div",Jo,[t[67]||(t[67]=e("label",null,"匹配文本",-1)),B(e("input",{"onUpdate:modelValue":t[28]||(t[28]=a=>c.value.condition_text=a),type:"text",class:"form-input",placeholder:"例如：测试通过、成功、无问题"},null,512),[[Y,c.value.condition_text]]),e("p",Wo,l(c.value.condition_type==="output_contains"?"当依赖节点输出包含此文本时，执行当前节点":"当依赖节点输出不包含此文本时，执行当前节点"),1)])])])):z("",!0)])):(o(),d("div",No,[(o(),k(w(g(Oe)),{size:16})),t[60]||(t[60]=e("span",null,"请先选择依赖节点，然后可以配置基于依赖输出的执行条件",-1))]))])):z("",!0),e("div",Xo,[t[69]||(t[69]=e("label",null,"系统提示词 (System Prompt)",-1)),B(e("textarea",{"onUpdate:modelValue":t[29]||(t[29]=a=>c.value.system_prompt=a),class:"form-textarea prompt-textarea",rows:"8",placeholder:`为这个智能体定义持久的系统级指令，例如：

你是一位资深的技术架构师，拥有15年的大型系统设计经验。你的职责是：
1. 评估技术方案的可行性和可扩展性
2. 识别潜在的技术风险和瓶颈
3. 提供具体的技术建议和最佳实践

请始终保持专业、客观，并提供可操作的建议。`},null,512),[[Y,c.value.system_prompt]]),t[70]||(t[70]=e("p",{class:"form-hint"}," `system_prompt` 会直接作为系统消息注入；如果这里留空，系统会自动用角色和任务生成默认系统提示。填写后会覆盖默认系统提示，但不会替代上面的 `task`。 ",-1))])])]),_:1},8,["model-value","title"])]))}}),Qo=ke(Yo,[["__scopeId","data-v-abf0ed89"]]),Ge=[{id:"document-analysis-pipeline",name:"文档深度分析",description:"理解文档 → 提取要点 → 分析问题 → 生成总结报告",category:"文档处理",mode:"pipeline",cross_review:!1,enable_skills:!0,agents:[{id:"reader",role:"文档理解专家",task:"通读文档，理解整体结构和核心内容",system_prompt:`你是文档理解专家，擅长快速把握文档的核心内容和结构。

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

在交叉评审中，请从受众角度评估其他人的修改建议`}]}],Zo=["全部","文档处理","内容创作","软件开发","问题诊断","决策支持"],el={class:"multiagent-config"},tl={class:"teams-list-view"},sl={class:"team-toolbar"},ol={class:"team-stats"},ll={class:"team-stat"},al={class:"team-stat"},nl={class:"team-actions"},il=["disabled"],rl={key:0,class:"team-filters"},dl={class:"team-search"},ul=["placeholder"],cl={value:""},ml={value:"pipeline"},pl={value:"graph"},vl={value:"council"},gl={value:""},fl={value:"active"},_l={value:"inactive"},yl={key:1,class:"team-state"},hl={key:2,class:"team-state"},bl={class:"team-state-desc"},kl={key:3,class:"team-empty"},$l={class:"team-empty-icon"},wl={class:"team-empty-title"},Cl={class:"team-empty-desc"},zl={class:"team-empty-actions"},Sl={key:4,class:"team-list"},Tl=["onClick"],Vl={class:"team-index"},Ml={class:"team-name-line"},Ul={class:"team-name"},Dl={class:"team-badge"},Al={key:0,class:"team-badge"},xl={key:1,class:"team-badge team-badge--muted"},El={class:"team-member-count"},Bl={class:"team-row-actions"},Ll=["title","onClick"],Pl=["title","onClick"],Nl={key:5,class:"team-state"},Ol={class:"team-state-title"},Fl={class:"team-state-desc"},Rl={class:"dialog-content"},jl={class:"template-hint"},ql={class:"template-categories"},Gl=["onClick"],Hl={class:"templates-grid"},Il=["onClick"],Jl={class:"template-header"},Wl={class:"template-badge"},Xl={class:"template-description"},Kl={class:"template-footer"},Yl={class:"template-agents"},Ql={class:"template-category"},Zl={class:"agent-form"},ea={class:"af-field"},ta={class:"af-label",for:"team-form-name"},sa=["placeholder"],oa={class:"af-field"},la={class:"af-label",for:"team-form-desc"},aa=["placeholder"],na={class:"af-field"},ia={class:"af-label"},ra={class:"mode-selector"},da=["onUpdate:modelValue","value"],ua={class:"mode-content"},ca={class:"af-switches"},ma={key:0,class:"af-switch-row"},pa={class:"af-switch-text"},va={class:"af-switch-title"},ga={class:"af-switch-hint"},fa={class:"af-switch-row"},_a={class:"af-switch-text"},ya={class:"af-switch-title"},ha={class:"af-switch-hint"},ba=["disabled"],ka=be({__name:"MultiAgentConfig",setup(h){const{t:p}=Ie(),m=Ye(),F=Qe(),{confirm:x}=Ke(),V=Q(()=>m.teams),J=Q(()=>V.value.filter(s=>s.is_active).length),W=Q(()=>m.loading),O=Q(()=>m.error),U=T(!1),P=T(!1),$=T(null),le=T(),X=T(""),N=T(""),D=T(""),H=T("全部"),oe=Q(()=>H.value==="全部"?Ge:Ge.filter(s=>s.category===H.value)),v=Q(()=>{let s=V.value;if(X.value.trim()){const u=X.value.toLowerCase();s=s.filter(i=>i.name.toLowerCase().includes(u)||i.description&&i.description.toLowerCase().includes(u))}if(N.value&&(s=s.filter(u=>u.mode===N.value)),D.value){const u=D.value==="active";s=s.filter(i=>i.is_active===u)}return s}),f=()=>{X.value="",N.value="",D.value=""},M=s=>{_.value={name:s.name,description:s.description,mode:s.mode,cross_review:s.cross_review,enable_skills:s.enable_skills,agents:JSON.parse(JSON.stringify(s.agents)),is_active:!0},P.value=!1,U.value=!0},_=T({name:"",description:"",mode:"council",cross_review:!0,enable_skills:!1,agents:[],is_active:!0}),r={pipeline:p("settings.multiagent.modePipeline"),graph:p("settings.multiagent.modeGraph"),council:p("settings.multiagent.modeCouncil")},A=[{id:"pipeline",name:p("settings.multiagent.modePipelineLong"),desc:p("settings.multiagent.modePipelineDesc")},{id:"graph",name:p("settings.multiagent.modeGraphLong"),desc:p("settings.multiagent.modeGraphDesc")},{id:"council",name:p("settings.multiagent.modeCouncilLong"),desc:p("settings.multiagent.modeCouncilDesc")}];Je(()=>I(this,null,function*(){yield ne()}));function q(){var s;(s=le.value)==null||s.click()}function E(){const s={version:"1.0.0",exported_at:new Date().toISOString(),teams:V.value.map(C=>({name:C.name,description:C.description||"",mode:C.mode,agents:C.agents,is_active:C.is_active,cross_review:C.cross_review,enable_skills:C.enable_skills}))},u=URL.createObjectURL(new Blob([JSON.stringify(s,null,2)],{type:"application/json"})),i=document.createElement("a");i.href=u,i.download=`agent-teams-${new Date().toISOString().slice(0,10)}.json`,i.click(),URL.revokeObjectURL(u)}function b(s){const u=String((s==null?void 0:s.name)||"").trim();if(!u)return null;const i=["pipeline","graph","council"].includes(s==null?void 0:s.mode)?s.mode:"pipeline";return{name:u,description:String((s==null?void 0:s.description)||""),mode:i,agents:(Array.isArray(s==null?void 0:s.agents)?s.agents:[]).filter(C=>C&&String(C.id||"").trim()).map(C=>{var R;return{id:String(C.id),role:String(C.role||""),system_prompt:C.system_prompt?String(C.system_prompt):null,task:String(C.task||""),perspective:C.perspective?String(C.perspective):null,depends_on:Array.isArray(C.depends_on)?C.depends_on.map(String):[],condition:(R=C.condition)!=null?R:null}}),is_active:(s==null?void 0:s.is_active)!==!1,cross_review:(s==null?void 0:s.cross_review)!==!1,enable_skills:!!(s!=null&&s.enable_skills)}}function c(s){return I(this,null,function*(){var C;const u=s.target,i=(C=u.files)==null?void 0:C[0];if(u.value="",!!i)try{const R=JSON.parse(yield i.text()),ve=Array.isArray(R)?R:R==null?void 0:R.teams;if(!Array.isArray(ve)||ve.length===0)throw new Error(p("settings.multiagent.noTeamData"));const de=ve.map(b).filter(Boolean);if(!de.length)throw new Error(p("settings.multiagent.noImportableTeams"));const ge=new Set;for(const Z of de){if(ge.has(Z.name))throw new Error(p("settings.multiagent.duplicateTeamName",{name:Z.name}));ge.add(Z.name)}const Se=new Map(V.value.map(Z=>[Z.name,Z]));for(const Z of de){const ue=Se.get(Z.name);ue?yield m.updateTeam(ue.id,Z):yield m.createTeam(Z)}yield ne(),F.success(p("settings.multiagent.importedTeams",{n:de.length}))}catch(R){F.error((R==null?void 0:R.message)||p("settings.multiagent.importFailed"))}})}const ne=()=>I(this,null,function*(){yield m.loadTeams()}),$e=s=>{$.value=s},we=s=>{s||($.value=null)},Ce=()=>I(this,null,function*(){if(yield m.loadTeams(),$.value){const s=V.value.find(u=>u.id===$.value.id);s&&($.value=s)}}),_e=s=>I(this,null,function*(){yield x({title:p("common.confirmDelete"),message:p("settings.multiagent.confirmDelete",{name:s.name}),type:"danger",confirmText:p("common.delete"),confirmVariant:"danger",onConfirm:()=>I(this,null,function*(){try{yield m.deleteTeam(s.id),F.success(p("common.success"))}catch(u){F.error(u.message||p("common.error"))}})})}),ie=s=>{const u={mode:s.mode,goal:p("settings.multiagent.goalPlaceholder"),cross_review:s.cross_review,agents:s.agents.map(i=>({id:i.id,role:i.role,perspective:i.perspective,task:i.task,depends_on:i.depends_on,system_prompt:i.system_prompt}))};navigator.clipboard.writeText(JSON.stringify(u,null,2)),F.success(p("common.copied"))},re=()=>{U.value=!1,_.value={name:"",description:"",mode:"council",cross_review:!0,enable_skills:!1,agents:[],is_active:!0}},ze=()=>I(this,null,function*(){if(!_.value.name.trim()){F.error(p("settings.multiagent.form.nameRequired"));return}try{const s=yield m.createTeam(_.value);F.success(p("settings.multiagent.form.createSuccess")),re(),$.value=s}catch(s){F.error(s.message||p("settings.multiagent.form.createError"))}});return(s,u)=>(o(),d("div",el,[e("div",tl,[e("div",sl,[e("div",ol,[e("span",ll,[e("b",null,l(J.value),1),L(" "+l(s.$t("settings.multiagent.activeCount")),1)]),u[14]||(u[14]=e("span",{class:"team-stat-sep","aria-hidden":"true"},null,-1)),e("span",al,[L(l(s.$t("settings.multiagent.totalCount"))+" ",1),e("b",null,l(V.value.length),1)])]),e("div",nl,[e("button",{class:"co-btn co-btn--secondary",onClick:q},[(o(),k(w(g(bt)),{size:14})),L(" "+l(s.$t("settings.multiagent.importTeams")),1)]),e("button",{class:"co-btn co-btn--secondary",disabled:!V.value.length,onClick:E},[(o(),k(w(g(kt)),{size:14})),L(" "+l(s.$t("settings.multiagent.exportTeams")),1)],8,il),e("button",{class:"co-btn co-btn--secondary",onClick:u[0]||(u[0]=i=>P.value=!0)},[(o(),k(w(g(je)),{size:14})),L(" "+l(s.$t("settings.multiagent.fromTemplate")),1)]),e("button",{class:"co-btn co-btn--primary",onClick:u[1]||(u[1]=i=>U.value=!0)},[(o(),k(w(g(We)),{size:14})),L(" "+l(s.$t("settings.multiagent.newTeam")),1)]),e("input",{ref_key:"importInput",ref:le,type:"file",accept:"application/json,.json",class:"import-file-input",onChange:c},null,544)])]),V.value.length>0?(o(),d("div",rl,[e("div",dl,[(o(),k(w(g(qe)),{size:14,class:"team-search-icon"})),B(e("input",{"onUpdate:modelValue":u[2]||(u[2]=i=>X.value=i),class:"team-search-input",type:"text",placeholder:s.$t("settings.multiagent.searchPlaceholder")},null,8,ul),[[Y,X.value]]),X.value?(o(),d("button",{key:0,class:"team-search-clear",onClick:u[3]||(u[3]=i=>X.value="")},[(o(),k(w(g(He)),{size:13}))])):z("",!0)]),B(e("select",{"onUpdate:modelValue":u[4]||(u[4]=i=>N.value=i),class:"co-select team-filter"},[e("option",cl,l(s.$t("settings.multiagent.allModes")),1),e("option",ml,l(s.$t("settings.multiagent.modePipeline")),1),e("option",pl,l(s.$t("settings.multiagent.modeGraph")),1),e("option",vl,l(s.$t("settings.multiagent.modeCouncil")),1)],512),[[fe,N.value]]),B(e("select",{"onUpdate:modelValue":u[5]||(u[5]=i=>D.value=i),class:"co-select team-filter"},[e("option",gl,l(s.$t("settings.multiagent.allStatus")),1),e("option",fl,l(s.$t("settings.multiagent.statusActive")),1),e("option",_l,l(s.$t("settings.multiagent.statusInactive")),1)],512),[[fe,D.value]])])):z("",!0),W.value?(o(),d("div",yl,[G(g(Dt))])):O.value?(o(),d("div",hl,[e("p",bl,l(O.value),1),e("button",{class:"co-btn co-btn--secondary",onClick:ne},l(s.$t("common.retry")),1)])):V.value.length===0?(o(),d("div",kl,[e("div",$l,[(o(),k(w(g(ye)),{size:22}))]),e("h3",wl,l(s.$t("settings.multiagent.empty")),1),e("p",Cl,l(s.$t("settings.multiagent.emptyDesc")),1),e("div",zl,[e("button",{class:"co-btn co-btn--secondary",onClick:u[6]||(u[6]=i=>P.value=!0)},[(o(),k(w(g(je)),{size:14})),L(" "+l(s.$t("settings.multiagent.fromTemplate")),1)]),e("button",{class:"co-btn co-btn--primary",onClick:u[7]||(u[7]=i=>U.value=!0)},l(s.$t("settings.multiagent.newTeam")),1)])])):v.value.length>0?(o(),d("div",Sl,[(o(!0),d(te,null,se(v.value,(i,C)=>(o(),d("div",{key:i.id,class:ee(["team-row",{"is-inactive":!i.is_active}]),onClick:R=>$e(i)},[e("span",Vl,l(String(C+1).padStart(2,"0")),1),e("div",Ml,[e("span",Ul,l(i.name),1),e("span",Dl,l(r[i.mode]),1),i.mode==="council"?(o(),d("span",Al,l(i.cross_review?s.$t("settings.multiagent.crossMode"):s.$t("settings.multiagent.independentMode")),1)):z("",!0),i.is_active?z("",!0):(o(),d("span",xl,l(s.$t("settings.multiagent.inactiveBadge")),1))]),e("span",El,[(o(),k(w(g(ye)),{size:12})),L(" "+l(i.agents.length)+" "+l(s.$t("settings.multiagent.agentUnit")),1)]),e("div",Bl,[e("button",{class:"icon-btn",title:s.$t("settings.multiagent.copyPayload"),onClick:xe(R=>ie(i),["stop"])},[(o(),k(w(g($t)),{size:15}))],8,Ll),e("button",{class:"icon-btn icon-btn--danger",title:s.$t("common.delete"),onClick:xe(R=>_e(i),["stop"])},[(o(),k(w(g(Xe)),{size:15}))],8,Pl)]),(o(),k(w(g(wt)),{size:15,class:"team-chevron"}))],10,Tl))),128))])):(o(),d("div",Nl,[(o(),k(w(g(qe)),{size:22,class:"team-state-icon"})),e("p",Ol,l(s.$t("settings.multiagent.noResults")),1),e("p",Fl,l(s.$t("settings.multiagent.noResultsDesc")),1),e("button",{class:"co-btn co-btn--secondary",onClick:f},l(s.$t("settings.multiagent.clearFilters")),1)])),G(g(he),{"model-value":P.value,onClose:u[8]||(u[8]=i=>P.value=!1),size:"large"},{default:ae(()=>[e("div",Rl,[e("h3",null,l(s.$t("settings.multiagent.templateTitle")),1),e("p",jl,l(s.$t("settings.multiagent.templateHint")),1),e("div",ql,[(o(!0),d(te,null,se(g(Zo),i=>(o(),d("button",{key:i,class:ee(["category-btn",{active:H.value===i}]),onClick:C=>H.value=i},l(i==="全部"?s.$t("settings.multiagent.allCategories"):i),11,Gl))),128))]),e("div",Hl,[(o(!0),d(te,null,se(oe.value,i=>(o(),d("div",{key:i.id,class:"template-card",onClick:C=>M(i)},[e("div",Jl,[e("h4",null,l(i.name),1),e("span",Wl,l(r[i.mode]),1)]),e("p",Xl,l(i.description),1),e("div",Kl,[e("span",Yl,[(o(),k(w(g(ye)),{size:14})),L(" "+l(s.$t("settings.multiagent.memberCount",{n:i.agents.length})),1)]),e("span",Ql,l(i.category),1)])],8,Il))),128))])])]),_:1},8,["model-value"]),G(g(he),{"model-value":U.value,title:s.$t("settings.multiagent.form.createTitle"),size:"medium",onClose:re},{footer:ae(()=>[e("button",{class:"co-btn co-btn--secondary",onClick:re},l(s.$t("common.cancel")),1),e("button",{class:"co-btn co-btn--primary",disabled:!_.value.name.trim(),onClick:ze},l(s.$t("settings.multiagent.form.createAndAddMembers")),9,ba)]),default:ae(()=>[e("div",Zl,[e("div",ea,[e("label",ta,[L(l(s.$t("settings.multiagent.form.name"))+" ",1),u[15]||(u[15]=e("span",{class:"af-required"},"*",-1))]),B(e("input",{id:"team-form-name","onUpdate:modelValue":u[9]||(u[9]=i=>_.value.name=i),type:"text",class:"co-input",placeholder:s.$t("settings.multiagent.form.namePlaceholder")},null,8,sa),[[Y,_.value.name]])]),e("div",oa,[e("label",la,l(s.$t("settings.multiagent.form.description")),1),B(e("textarea",{id:"team-form-desc","onUpdate:modelValue":u[10]||(u[10]=i=>_.value.description=i),class:"co-textarea",rows:"3",placeholder:s.$t("settings.multiagent.form.descriptionPlaceholder")},null,8,aa),[[Y,_.value.description]])]),e("div",na,[e("span",ia,[L(l(s.$t("settings.multiagent.form.mode"))+" ",1),u[16]||(u[16]=e("span",{class:"af-required"},"*",-1))]),e("div",ra,[(o(),d(te,null,se(A,i=>e("label",{key:i.id,class:ee(["mode-option",{selected:_.value.mode===i.id}])},[B(e("input",{"onUpdate:modelValue":C=>_.value.mode=C,type:"radio",value:i.id,class:"mode-input"},null,8,da),[[Ct,_.value.mode]]),u[17]||(u[17]=e("span",{class:"mode-radio","aria-hidden":"true"},null,-1)),e("span",ua,[e("strong",null,l(i.name),1),e("span",null,l(i.desc),1)])],2)),64))])]),e("div",ca,[_.value.mode==="council"?(o(),d("div",ma,[e("div",pa,[e("span",va,l(s.$t("settings.multiagent.form.crossReview")),1),e("span",ga,l(s.$t("settings.multiagent.form.crossReviewHint")),1)]),G(pe,{modelValue:_.value.cross_review,"onUpdate:modelValue":u[11]||(u[11]=i=>_.value.cross_review=i),width:40,height:22,"aria-label":s.$t("settings.multiagent.form.crossReview")},null,8,["modelValue","aria-label"])])):z("",!0),e("div",fa,[e("div",_a,[e("span",ya,l(s.$t("settings.multiagent.form.enableSkills")),1),e("span",ha,l(s.$t("settings.multiagent.form.enableSkillsHint")),1)]),G(pe,{modelValue:_.value.enable_skills,"onUpdate:modelValue":u[12]||(u[12]=i=>_.value.enable_skills=i),width:40,height:22,"aria-label":s.$t("settings.multiagent.form.enableSkills")},null,8,["modelValue","aria-label"])])])])]),_:1},8,["model-value","title"])]),G(g(Gt),{"model-value":!!$.value,size:"wide","show-header":!1,"mask-closable":!0,"onUpdate:modelValue":we},{default:ae(()=>[$.value?(o(),k(Qo,{key:0,team:$.value,onBack:u[13]||(u[13]=i=>$.value=null),onUpdated:Ce},null,8,["team"])):z("",!0)]),_:1},8,["model-value"])]))}}),Ma=ke(ka,[["__scopeId","data-v-469d2ad5"]]);export{Ma as default};
