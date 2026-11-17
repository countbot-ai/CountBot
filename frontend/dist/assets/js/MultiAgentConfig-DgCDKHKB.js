var et=Object.defineProperty;var Be=Object.getOwnPropertySymbols;var tt=Object.prototype.hasOwnProperty,st=Object.prototype.propertyIsEnumerable;var Le=(y,w,m)=>w in y?et(y,w,{enumerable:!0,configurable:!0,writable:!0,value:m}):y[w]=m,Pe=(y,w)=>{for(var m in w||(w={}))tt.call(w,m)&&Le(y,m,w[m]);if(Be)for(var m of Be(w))st.call(w,m)&&Le(y,m,w[m]);return y};var G=(y,w,m)=>new Promise((R,A)=>{var V=O=>{try{W(m.next(O))}catch(T){A(T)}},J=O=>{try{W(m.throw(O))}catch(T){A(T)}},W=O=>O.done?R(O.value):Promise.resolve(O.value).then(V,J);W((m=m.apply(y,w)).next())});import{b as he,F as De,at as ot,o as s,j as h,G as H,T as lt,H as ae,e as u,f as e,x as Ae,n as ee,g as xe,h as L,t as n,k as $,l as v,X as Ie,i as z,au as at,c as Q,r as x,_ as ke,av as nt,aw as it,I as te,J as se,ax as rt,ay as dt,D as Ge,u as ut,q as Je,az as ct,a7 as Ne,aA as mt,a5 as We,aB as ye,a9 as Xe,af as be,aC as Oe,aD as pt,y as B,aE as Re,z as Y,U as ge,aa as vt,aF as ft,aG as gt,ag as _t,aj as je,aH as yt,aI as bt,ab as Ke,aJ as ht,aK as kt,aL as qe,aM as Fe,a8 as $t,aN as wt,aO as Ct}from"./index-BRW75nvj.js";import{i as Ye,j as Ve,k as zt,l as Me,M as St,S as pe,m as xt,n as Vt,o as Mt,b as Qe}from"./agentTeams-BgjzJk9i.js";import{M as Tt,L as Ut}from"./useKeyboard-DIR7xHFo.js";import{u as Dt}from"./useModelCatalog-D2lor1WA.js";import{r as At,a as Et,f as Bt,b as Lt}from"./providerRuntime-Bim9Xk0P.js";import"./countbot-logo-CNglRKg-.js";const Pt=["aria-labelledby"],Nt={key:0,class:"drawer-header"},Ot=["id"],Rt=["aria-label"],jt={class:"drawer-body"},qt={key:1,class:"drawer-footer"},Ft=he({__name:"Drawer",props:{modelValue:{type:Boolean},title:{default:""},size:{default:"medium"},placement:{default:"right"},closable:{type:Boolean,default:!0},maskClosable:{type:Boolean,default:!1},showHeader:{type:Boolean,default:!0}},emits:["update:modelValue","close"],setup(y,{emit:w}){const m=y,R=w,A=Q(()=>`drawer-title-${Math.random().toString(36).slice(2,9)}`),V=x(),J=()=>{R("update:modelValue",!1),R("close")},W=()=>{m.maskClosable&&J()},O=T=>{T.key==="Escape"&&m.modelValue&&m.closable&&J()};return De(()=>m.modelValue,T=>{document.body.style.overflow=T?"hidden":"",T?(document.addEventListener("keydown",O),setTimeout(()=>{var k;const P=(k=V.value)==null?void 0:k.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');P==null||P.focus()},60)):document.removeEventListener("keydown",O)},{immediate:!0}),ot(()=>{document.removeEventListener("keydown",O),document.body.style.overflow=""}),(T,P)=>(s(),h(at,{to:"body"},[H(lt,{name:"drawer"},{default:ae(()=>[y.modelValue?(s(),u("div",{key:0,class:"drawer-overlay",onClick:W},[e("aside",{ref_key:"panelRef",ref:V,class:ee(["drawer-panel",[`drawer-${y.size}`,`drawer-${y.placement}`]]),role:"dialog","aria-modal":"true","aria-labelledby":A.value,onClick:P[0]||(P[0]=Ae(()=>{},["stop"]))},[y.showHeader?(s(),u("header",Nt,[e("h2",{id:A.value,class:"drawer-title"},[xe(T.$slots,"title",{},()=>[L(n(y.title),1)],!0)],8,Ot),y.closable?(s(),u("button",{key:0,type:"button",class:"drawer-close","aria-label":T.$t("common.close"),onClick:J},[(s(),h($(v(Ie)),{size:18}))],8,Rt)):z("",!0)])):z("",!0),e("div",jt,[xe(T.$slots,"default",{},void 0,!0)]),T.$slots.footer?(s(),u("footer",qt,[xe(T.$slots,"footer",{},void 0,!0)])):z("",!0)],10,Pt)])):z("",!0)]),_:3})]))}}),Ht=ke(Ft,[["__scopeId","data-v-b1db600d"]]),It={class:"dependency-graph"},Gt={class:"graph-header"},Jt={class:"graph-controls"},Wt={id:"arrowhead",markerWidth:"10",markerHeight:"10",refX:"9",refY:"3",orient:"auto"},Xt=["fill"],Kt={class:"edges"},Yt=["x1","y1","x2","y2","marker-end"],Qt={class:"nodes"},Zt=["transform","onClick","onMouseenter"],es=["x","y"],ts={class:"node-label","text-anchor":"middle",dy:"0.3em"},ss=["y"],os={class:"tooltip-content"},ls={key:0},as={key:1,class:"tooltip-deps"},ns={key:0,class:"cycle-warning"},Te=140,me=60,Ue=200,is=120,rs=he({__name:"DependencyGraph",props:{agents:{}},setup(y){const w=y,m=x(),R=x(),A=x(null),V=x(null),J=Q(()=>typeof window!="undefined"&&m.value&&getComputedStyle(m.value).getPropertyValue("--text-tertiary").trim()||"var(--text-tertiary)"),W=()=>{const g=new Map,p=new Set,M=f=>{if(p.has(f))return g.get(f)||0;p.add(f);const d=w.agents.find(E=>E.id===f);if(!d||!d.depends_on||d.depends_on.length===0)return g.set(f,0),0;const F=Math.max(...d.depends_on.map(E=>M(E)))+1;return g.set(f,F),F};return w.agents.forEach(f=>M(f.id)),g},O=()=>{const g=[],p=new Set,M=new Set,f=[],d=D=>{p.add(D),M.add(D),f.push(D);const F=w.agents.find(E=>E.id===D);if(F!=null&&F.depends_on){for(const E of F.depends_on)if(p.has(E)){if(M.has(E)){const b=f.indexOf(E);return g.push(f.slice(b)),!0}}else if(d(E))return!0}return f.pop(),M.delete(D),!1};return w.agents.forEach(D=>{p.has(D.id)||d(D.id)}),g},T=Q(()=>O()),P=Q(()=>{const g=W(),p=new Map,M=w.agents.map(d=>({id:d.id,label:d.role||d.id,task:d.task,depends_on:d.depends_on||[],hasCondition:!!d.condition,x:0,y:0,level:g.get(d.id)||0}));M.forEach(d=>{const D=d.level;p.has(D)||p.set(D,[]),p.get(D).push(d)});const f=800;return p.forEach((d,D)=>{const F=d.length*Ue,E=(f-F)/2+Ue/2,b=80+D*is;d.forEach((c,ne)=>{c.x=E+ne*Ue,c.y=b})}),M}),k=Q(()=>{const g=[];return P.value.forEach(p=>{p.depends_on.forEach(M=>{const f=P.value.find(d=>d.id===M);f&&g.push({from:M,to:p.id,x1:f.x,y1:f.y+me/2,x2:p.x,y2:p.y-me/2})})}),g}),le=g=>{A.value=A.value===g?null:g},X=g=>{if(!A.value)return!1;const p=P.value.find(M=>M.id===A.value);return p?g.from===A.value||g.to===A.value||p.depends_on.includes(g.from)||P.value.some(M=>M.depends_on.includes(A.value)&&M.id===g.to):!1},N=g=>P.value.find(p=>p.id===g),U=g=>{const p=N(g);return p?{left:`${p.x+Te/2+10}px`,top:`${p.y-me/2}px`}:{}},I=()=>{A.value=null},oe=()=>{A.value=null};return(g,p)=>{var M,f,d,D,F,E;return s(),u("div",It,[e("div",Gt,[p[1]||(p[1]=e("h3",null,"依赖关系图",-1)),e("div",Jt,[e("button",{class:"control-btn",onClick:I,title:"重置视图"},[(s(),h($(v(nt)),{size:16}))]),e("button",{class:"control-btn",onClick:oe,title:"自动布局"},[(s(),h($(v(it)),{size:16}))])])]),e("div",{ref_key:"graphContainer",ref:m,class:"graph-container"},[(s(),u("svg",{ref_key:"svgElement",ref:R,class:"graph-svg"},[e("defs",null,[e("marker",Wt,[e("polygon",{points:"0 0, 10 3, 0 6",fill:J.value},null,8,Xt)]),p[2]||(p[2]=e("marker",{id:"arrowhead-highlighted",markerWidth:"10",markerHeight:"10",refX:"9",refY:"3",orient:"auto"},[e("polygon",{points:"0 0, 10 3, 0 6",fill:"var(--color-accent)"})],-1))]),e("g",Kt,[(s(!0),u(te,null,se(k.value,b=>(s(),u("line",{key:`${b.from}-${b.to}`,x1:b.x1,y1:b.y1,x2:b.x2,y2:b.y2,class:ee(["edge",{highlighted:X(b)}]),"marker-end":X(b)?"url(#arrowhead-highlighted)":"url(#arrowhead)"},null,10,Yt))),128))]),e("g",Qt,[(s(!0),u(te,null,se(P.value,b=>(s(),u("g",{key:b.id,transform:`translate(${b.x}, ${b.y})`,class:ee(["node",{highlighted:A.value===b.id,"has-condition":b.hasCondition}]),onClick:c=>le(b.id),onMouseenter:c=>V.value=b.id,onMouseleave:p[0]||(p[0]=c=>V.value=null)},[e("rect",{width:Te,height:me,x:-Te/2,y:-me/2,rx:"8",class:"node-rect"},null,8,es),e("text",ts,n(b.label),1),b.hasCondition?(s(),u("text",{key:0,class:"condition-indicator","text-anchor":"middle",y:me/2-8,"font-size":"10"}," ⚡ 条件执行 ",8,ss)):z("",!0)],42,Zt))),128))])],512)),V.value?(s(),u("div",{key:0,class:"node-tooltip",style:rt(U(V.value))},[e("div",os,[e("strong",null,n((M=N(V.value))==null?void 0:M.label),1),(f=N(V.value))!=null&&f.task?(s(),u("p",ls,n((d=N(V.value))==null?void 0:d.task),1)):z("",!0),(F=(D=N(V.value))==null?void 0:D.depends_on)!=null&&F.length?(s(),u("div",as,[p[3]||(p[3]=e("span",{class:"tooltip-label"},"依赖:",-1)),L(" "+n((E=N(V.value))==null?void 0:E.depends_on.join(", ")),1)])):z("",!0)])],4)):z("",!0)],512),T.value.length>0?(s(),u("div",ns,[(s(),h($(v(dt)),{size:16})),e("div",null,[p[4]||(p[4]=e("strong",null,"检测到循环依赖！",-1)),(s(!0),u(te,null,se(T.value,(b,c)=>(s(),u("p",{key:c},n(b.join(" → "))+" → "+n(b[0]),1))),128))])])):z("",!0)])}}}),ds=ke(rs,[["__scopeId","data-v-3f62dead"]]),us={class:"team-detail"},cs={class:"detail-header"},ms={class:"team-info-section"},ps={class:"team-title-row"},vs={class:"team-badges"},fs={class:"badge badge-mode"},gs={key:0,class:"team-description"},_s={class:"members-section"},ys={class:"section-header"},bs={class:"section-actions"},hs={key:0,class:"graph-section"},ks={key:1,class:"empty-members"},$s={key:2,class:"members-list"},ws={class:"member-header"},Cs={class:"member-info"},zs={class:"member-number"},Ss={class:"member-actions"},xs=["onClick"],Vs=["onClick"],Ms={class:"member-details"},Ts={class:"detail-item"},Us={class:"detail-value"},Ds={key:0,class:"detail-item"},As={class:"detail-value"},Es={key:1,class:"detail-item"},Bs={class:"detail-value"},Ls={key:2,class:"detail-item"},Ps={class:"detail-value"},Ns={key:3,class:"detail-item full-width"},Os={class:"condition-badge"},Rs={class:"condition-type"},js={class:"condition-node"},qs={class:"condition-text"},Fs={key:4,class:"detail-item full-width"},Hs={class:"prompt-preview"},Is={class:"dialog-content"},Gs={class:"tabs-nav"},Js={class:"tabs-content"},Ws={class:"tab-panel"},Xs={class:"form-group"},Ks={class:"form-group"},Ys={class:"form-group"},Qs={key:0,class:"form-group"},Zs={class:"toggle-wrapper"},eo={class:"form-group"},to={class:"toggle-wrapper"},so={key:0,class:"tab-panel"},oo={class:"toggle-header"},lo={class:"toggle-label"},ao={key:0,class:"config-badge"},no={key:0,class:"model-config-section"},io={class:"form-grid"},ro={class:"form-group"},uo={class:"form-group"},co={class:"advanced-config"},mo={class:"advanced-content"},po={class:"form-group"},vo=["placeholder"],fo={class:"form-hint"},go={class:"form-group"},_o=["placeholder"],yo={class:"form-hint"},bo={class:"form-group"},ho=["disabled"],ko={key:1,class:"empty-state-inline"},$o={class:"dialog-content"},wo={class:"form-group"},Co={key:0,class:"form-group"},zo={key:1,class:"form-group"},So={key:2,class:"form-group"},xo={key:3,class:"form-group"},Vo={class:"dependency-selector"},Mo={key:0,class:"selected-tags"},To=["onClick"],Uo=["disabled"],Do={value:""},Ao=["value"],Eo={key:4,class:"form-group"},Bo={key:0,class:"condition-disabled-hint"},Lo={key:1,class:"condition-config"},Po={class:"toggle-wrapper"},No={key:0,class:"condition-form"},Oo={class:"form-row"},Ro={class:"form-col"},jo={class:"form-col"},qo=["value"],Fo={class:"form-row"},Ho={class:"form-col full"},Io={class:"form-hint"},Go={class:"form-group"},Jo=["disabled"],Wo=he({__name:"TeamDetail",props:{team:{}},emits:["back","updated"],setup(y,{emit:w}){const m=y,R=w,{t:A}=Ge(),V=Ye(),J=ut(),W=Qe(),O=Dt(),{confirm:T}=Ke(),P={pipeline:"流水线",graph:"依赖图",council:"多视角"},k=x([]),le=x(!1),X=x(!1),N=x("basic"),U=x({name:"",description:"",mode:"council",cross_review:!0,enable_skills:!1}),I=x(!1),oe=x(!1),g=x(null),p=x([]),M=x(!1),f=()=>Me(),d=x(f()),D=x(f()),F=Q(()=>p.value.map(a=>({value:a.id,label:a.name}))),E=x(!1),b=x(null),c=x({id:"",role:"",perspective:"",task:"",system_prompt:"",depends_on_str:"",enable_condition:!1,condition_type:"output_contains",condition_node:"",condition_text:""}),ne=Q(()=>c.value.id.trim()?m.team.mode==="council"?!!c.value.perspective.trim():!!c.value.role.trim():!1);De(()=>m.team,a=>{a&&(k.value=JSON.parse(JSON.stringify(a.agents||[])),U.value={name:a.name,description:a.description||"",mode:a.mode,cross_review:a.cross_review,enable_skills:a.enable_skills||!1})},{immediate:!0}),Je(()=>G(this,null,function*(){yield j(),yield ve()}));const $e=()=>{b.value=null,c.value={id:`agent${k.value.length+1}`,role:"",perspective:"",task:"",system_prompt:"",depends_on_str:"",enable_condition:!1,condition_type:"output_contains",condition_node:"",condition_text:""},E.value=!0},we=a=>{var _,q,K;b.value=a;const t=k.value[a],l=!!t.condition;c.value={id:t.id,role:t.role||"",perspective:t.perspective||"",task:t.task||"",system_prompt:t.system_prompt||"",depends_on_str:(t.depends_on||[]).join(", "),enable_condition:l,condition_type:((_=t.condition)==null?void 0:_.type)||"output_contains",condition_node:((q=t.condition)==null?void 0:q.node)||"",condition_text:((K=t.condition)==null?void 0:K.text)||""},E.value=!0},Ce=()=>{const a=new Set,t=[];for(c.value.depends_on_str.split(",").map(_=>_.trim()).filter(Boolean).forEach(_=>{a.add(_),t.push(_)});t.length>0;){const _=t.shift(),q=k.value.find(K=>K.id===_);q!=null&&q.depends_on&&q.depends_on.forEach(K=>{a.has(K)||(a.add(K),t.push(K))})}return Array.from(a)},_e=a=>k.value.find(t=>t.id===a),ie=()=>c.value.depends_on_str.split(",").map(a=>a.trim()).filter(Boolean),re=()=>{const a=c.value.id.trim(),t=ie();return k.value.filter(l=>{if(b.value!==null){const _=k.value[b.value];if(l.id===(_==null?void 0:_.id))return!1}return l.id===a?!1:!t.includes(l.id)})},ze=a=>{const t=a.target,l=t.value;if(!l)return;const _=ie();_.push(l),c.value.depends_on_str=_.join(", "),t.value=""},o=a=>{const l=ie().filter(_=>_!==a);c.value.depends_on_str=l.join(", "),l.length===0&&(c.value.enable_condition=!1,c.value.condition_node="",c.value.condition_text="")},i=a=>G(this,null,function*(){(yield T({title:"确认删除",message:"确定要删除这个成员吗？",type:"danger",confirmText:"删除",confirmVariant:"danger"}))&&(k.value.splice(a,1),Ee())}),r=()=>{E.value=!1,b.value=null},C=()=>{const a={id:c.value.id.trim()};if(m.team.mode==="council"){a.perspective=c.value.perspective.trim();const t=a.perspective.split(/[，,]/);a.role=t[0].trim()||a.id}else a.role=c.value.role.trim(),a.task=c.value.task.trim();c.value.system_prompt.trim()&&(a.system_prompt=c.value.system_prompt.trim()),m.team.mode==="graph"?(a.depends_on=c.value.depends_on_str.split(",").map(t=>t.trim()).filter(Boolean),c.value.enable_condition&&c.value.condition_node&&c.value.condition_text.trim()&&(a.condition={type:c.value.condition_type,node:c.value.condition_node,text:c.value.condition_text.trim()})):a.depends_on=[],b.value!==null?k.value[b.value]=a:k.value.push(a),r(),Ee()};function j(){return G(this,null,function*(){try{const a=yield O.listProviders();p.value=a.map(t=>({id:t.id,name:t.name,defaultApiBase:Et(t),defaultModel:At(t)})),fe()}catch(a){}})}function ve(){return G(this,null,function*(){if(!(!m.team.id||!J.isAdmin))try{const a=yield Ve.getConfig(m.team.id);D.value=zt(void 0,a.global_defaults),a.use_custom_model?de(a.model_settings,!0):de(a.global_defaults,!1)}catch(a){}})}function de(a,t){M.value=!0;try{I.value=t,d.value=Me(D.value,t?a:void 0),g.value=null,fe()}finally{M.value=!1}}function fe(){if(p.value.length===0||Bt(p.value,d.value.provider))return;const l=Lt(p.value)||p.value[0];l&&(d.value.provider=l.id,d.value.api_base||(d.value.api_base=l.defaultApiBase||""),(!d.value.model||d.value.model===St.model)&&(d.value.model=l.defaultModel||d.value.model))}function Se(){if(!I.value){g.value=null;return}d.value=Me(D.value,d.value),g.value=null}function Z(){return G(this,null,function*(){var a,t;oe.value=!0,g.value=null;try{const l=yield O.testConnection(Pe({provider:d.value.provider||"zhipu",api_key:d.value.api_key||void 0,api_base:d.value.api_base||void 0,model:d.value.model||"glm-5"},Vt(d.value)));g.value={success:l.success,message:l.success?l.message||A("settings.providers.testSuccess"):l.error||l.message||A("settings.providers.testFailed")}}catch(l){g.value={success:!1,message:((t=(a=l.response)==null?void 0:a.data)==null?void 0:t.error)||l.message||A("settings.providers.testFailed")}}finally{oe.value=!1}})}De(()=>d.value.provider,(a,t)=>{if(!a||p.value.length===0||M.value)return;const l=p.value.find(ce=>ce.id===a),_=t?p.value.find(ce=>ce.id===t):null;if(!l)return;(!d.value.api_base||!!(_!=null&&_.defaultApiBase)&&d.value.api_base===_.defaultApiBase)&&(d.value.api_base=l.defaultApiBase||""),(!d.value.model||!!(_!=null&&_.defaultModel)&&d.value.model===_.defaultModel)&&l.defaultModel&&(d.value.model=l.defaultModel)});const ue=()=>{X.value=!1,N.value="basic"},Ze=()=>G(this,null,function*(){try{yield V.updateTeam(m.team.id,{name:U.value.name,description:U.value.description,mode:U.value.mode,cross_review:U.value.cross_review,enable_skills:U.value.enable_skills,agents:k.value,is_active:m.team.is_active}),J.isAdmin&&(I.value?yield Ve.updateConfig(m.team.id,Mt(d.value,D.value)):m.team.use_custom_model&&(yield Ve.resetConfig(m.team.id))),W.success("团队信息已更新"),ue(),R("updated")}catch(a){W.error(a.message||"保存失败")}}),Ee=()=>G(this,null,function*(){try{yield V.updateTeam(m.team.id,{name:m.team.name,description:m.team.description,mode:m.team.mode,cross_review:m.team.cross_review,enable_skills:m.team.enable_skills||!1,agents:k.value,is_active:m.team.is_active}),W.success("成员已更新"),R("updated")}catch(a){W.error(a.message||"保存失败")}});return(a,t)=>(s(),u("div",us,[e("div",cs,[e("button",{class:"btn-back",onClick:t[0]||(t[0]=l=>a.$emit("back"))},[(s(),h($(v(ct)),{size:16})),t[30]||(t[30]=L(" 返回团队列表 ",-1))]),e("div",ms,[e("div",ps,[e("h2",null,n(y.team.name),1),e("div",vs,[e("span",fs,n(P[y.team.mode]),1),y.team.mode==="council"?(s(),u("span",{key:0,class:ee(["badge badge-review",y.team.cross_review?"badge-cross":"badge-independent"])},n(y.team.cross_review?"交叉模式":"独立模式"),3)):z("",!0)]),e("button",{class:"icon-btn",onClick:t[1]||(t[1]=l=>X.value=!0)},[(s(),h($(v(Ne)),{size:16}))])]),y.team.description?(s(),u("p",gs,n(y.team.description),1)):z("",!0)])]),e("div",_s,[e("div",ys,[e("h3",null,"团队成员 ("+n(k.value.length)+")",1),e("div",bs,[y.team.mode==="graph"&&k.value.length>0?(s(),u("button",{key:0,class:"btn-secondary",onClick:t[2]||(t[2]=l=>le.value=!le.value)},[(s(),h($(v(mt)),{size:16})),L(" "+n(le.value?"隐藏依赖图":"查看依赖图"),1)])):z("",!0),e("button",{class:"btn-primary",onClick:$e},[(s(),h($(v(We)),{size:16})),t[31]||(t[31]=L(" 添加成员 ",-1))])])]),y.team.mode==="graph"&&le.value&&k.value.length>0?(s(),u("div",hs,[H(ds,{agents:k.value},null,8,["agents"])])):z("",!0),k.value.length===0?(s(),u("div",ks,[(s(),h($(v(ye)),{size:48,class:"empty-icon"})),t[32]||(t[32]=e("p",null,"暂无成员，点击上方按钮添加",-1))])):(s(),u("div",$s,[(s(!0),u(te,null,se(k.value,(l,_)=>{var q;return s(),u("div",{key:_,class:"member-card"},[e("div",ws,[e("div",Cs,[e("span",zs,"#"+n(_+1),1),e("h4",null,n(l.role||l.perspective||l.id),1)]),e("div",Ss,[e("button",{class:"icon-btn",onClick:K=>we(_)},[(s(),h($(v(Ne)),{size:16}))],8,xs),e("button",{class:"icon-btn danger",onClick:K=>i(_)},[(s(),h($(v(Xe)),{size:16}))],8,Vs)])]),e("div",Ms,[e("div",Ts,[t[33]||(t[33]=e("span",{class:"detail-label"},"ID:",-1)),e("span",Us,n(l.id),1)]),y.team.mode==="council"?(s(),u("div",Ds,[t[34]||(t[34]=e("span",{class:"detail-label"},"视角:",-1)),e("span",As,n(l.perspective||"-"),1)])):(s(),u("div",Es,[t[35]||(t[35]=e("span",{class:"detail-label"},"任务:",-1)),e("span",Bs,n(l.task||"-"),1)])),y.team.mode==="graph"&&((q=l.depends_on)!=null&&q.length)?(s(),u("div",Ls,[t[36]||(t[36]=e("span",{class:"detail-label"},"依赖:",-1)),e("span",Ps,n(l.depends_on.join(", ")),1)])):z("",!0),l.condition?(s(),u("div",Ns,[t[37]||(t[37]=e("span",{class:"detail-label"},"执行条件:",-1)),e("div",Os,[e("span",Rs,n(l.condition.type==="output_contains"?"包含":"不包含"),1),e("span",js,n(l.condition.node),1),e("span",qs,'"'+n(l.condition.text)+'"',1)])])):z("",!0),l.system_prompt?(s(),u("div",Fs,[t[38]||(t[38]=e("span",{class:"detail-label"},"系统提示词:",-1)),e("div",Hs,n(l.system_prompt),1)])):z("",!0)])])}),128))]))]),H(v(be),{"model-value":X.value,title:"编辑团队信息",size:"large",onClose:ue},{footer:ae(()=>[e("button",{class:"co-btn co-btn--secondary",onClick:ue},"取消"),e("button",{class:"co-btn co-btn--primary",onClick:Ze},"保存")]),default:ae(()=>{var l,_,q,K,ce;return[e("div",Is,[e("div",Gs,[e("button",{class:ee(["tab-btn",{active:N.value==="basic"}]),onClick:t[3]||(t[3]=S=>N.value="basic")},[(s(),h($(v(Oe)),{size:16})),t[39]||(t[39]=e("span",null,"基本信息",-1))],2),v(J).isAdmin?(s(),u("button",{key:0,class:ee(["tab-btn",{active:N.value==="model"}]),onClick:t[4]||(t[4]=S=>N.value="model")},[(s(),h($(v(pt)),{size:16})),t[40]||(t[40]=e("span",null,"模型配置",-1))],2)):z("",!0)]),e("div",Js,[B(e("div",Ws,[e("div",Xs,[t[41]||(t[41]=e("label",null,[L("团队名称 "),e("span",{class:"required"},"*")],-1)),B(e("input",{"onUpdate:modelValue":t[5]||(t[5]=S=>U.value.name=S),type:"text",class:"form-input"},null,512),[[Y,U.value.name]])]),e("div",Ks,[t[42]||(t[42]=e("label",null,"团队描述",-1)),B(e("textarea",{"onUpdate:modelValue":t[6]||(t[6]=S=>U.value.description=S),class:"form-textarea",rows:"3"},null,512),[[Y,U.value.description]])]),e("div",Ys,[t[44]||(t[44]=e("label",null,[L("协作模式 "),e("span",{class:"required"},"*")],-1)),B(e("select",{"onUpdate:modelValue":t[7]||(t[7]=S=>U.value.mode=S),class:"form-select"},[...t[43]||(t[43]=[e("option",{value:"pipeline"},"流水线 (Pipeline)",-1),e("option",{value:"graph"},"依赖图 (Graph)",-1),e("option",{value:"council"},"多视角 (Council)",-1)])],512),[[ge,U.value.mode]])]),U.value.mode==="council"?(s(),u("div",Qs,[e("div",Zs,[t[45]||(t[45]=e("div",{class:"toggle-content"},[e("span",{class:"toggle-title"},"启用交叉评审"),e("p",{class:"toggle-hint"},"关闭后，成员将独立分析，不互相评审")],-1)),H(pe,{modelValue:U.value.cross_review,"onUpdate:modelValue":t[8]||(t[8]=S=>U.value.cross_review=S),width:44,height:24,"aria-label":"启用交叉评审"},null,8,["modelValue"])])])):z("",!0),e("div",eo,[e("div",to,[t[46]||(t[46]=e("div",{class:"toggle-content"},[e("span",{class:"toggle-title"},"启用技能系统"),e("p",{class:"toggle-hint"},"开启后，子 Agent 可以使用技能（如图片生成、天气查询等）")],-1)),H(pe,{modelValue:U.value.enable_skills,"onUpdate:modelValue":t[9]||(t[9]=S=>U.value.enable_skills=S),width:44,height:24,"aria-label":"启用技能系统"},null,8,["modelValue"])])])],512),[[Re,N.value==="basic"]]),v(J).isAdmin?B((s(),u("div",so,[e("div",{class:ee(["config-toggle",{active:I.value}])},[e("div",oo,[e("label",lo,[H(pe,{modelValue:I.value,"onUpdate:modelValue":t[10]||(t[10]=S=>I.value=S),width:48,height:28,"aria-label":"为此团队使用自定义模型",onChange:Se},null,8,["modelValue"]),t[47]||(t[47]=e("div",{class:"toggle-content-large"},[e("span",{class:"toggle-text"},"为此团队使用自定义模型"),e("span",{class:"toggle-hint"},"团队成员将使用此配置的模型和 API")],-1))]),I.value?(s(),u("div",ao,[(s(),h($(v(vt)),{size:14})),t[48]||(t[48]=e("span",null,"自定义",-1))])):z("",!0)])],2),I.value?(s(),u("div",no,[t[49]||(t[49]=e("div",{class:"model-config-toolbar"},[e("div",{class:"model-config-copy"},[e("h4",null,"模型设置")])],-1)),e("div",io,[e("div",ro,[e("label",null,n(a.$t("settings.providers.selectProvider")),1),H(xt,{modelValue:d.value.provider,"onUpdate:modelValue":t[11]||(t[11]=S=>d.value.provider=S),options:F.value,placeholder:a.$t("settings.providers.selectProvider"),searchable:""},null,8,["modelValue","options","placeholder"])]),e("div",uo,[e("label",null,n(a.$t("settings.providers.model")),1),B(e("input",{"onUpdate:modelValue":t[12]||(t[12]=S=>d.value.model=S),type:"text",class:"form-input",placeholder:"glm-5"},null,512),[[Y,d.value.model]])])]),H(Tt,{temperature:(l=d.value.temperature)!=null?l:0,"max-tokens":(_=d.value.max_tokens)!=null?_:0,"max-iterations":(q=d.value.max_iterations)!=null?q:0,"thinking-enabled":(K=d.value.thinking_enabled)!=null?K:!0,"stream-enabled":(ce=d.value.stream_enabled)!=null?ce:!0,"onUpdate:temperature":t[13]||(t[13]=S=>d.value.temperature=S),"onUpdate:maxTokens":t[14]||(t[14]=S=>d.value.max_tokens=S),"onUpdate:maxIterations":t[15]||(t[15]=S=>d.value.max_iterations=S),"onUpdate:thinkingEnabled":t[16]||(t[16]=S=>d.value.thinking_enabled=S),"onUpdate:streamEnabled":t[17]||(t[17]=S=>d.value.stream_enabled=S)},null,8,["temperature","max-tokens","max-iterations","thinking-enabled","stream-enabled"]),e("details",co,[e("summary",null,[(s(),h($(v(ft)),{size:16})),e("span",null,n(a.$t("chat.sessionConfig.advancedApiSettings")),1),(s(),h($(v(gt)),{size:16,class:"chevron"}))]),e("div",mo,[e("div",po,[e("label",null,n(a.$t("settings.providers.apiKey")),1),B(e("input",{"onUpdate:modelValue":t[18]||(t[18]=S=>d.value.api_key=S),type:"password",placeholder:a.$t("chat.sessionConfig.leaveEmptyForGlobal"),class:"form-input"},null,8,vo),[[Y,d.value.api_key]]),e("p",fo,n(a.$t("chat.sessionConfig.apiKeyHint")),1)]),e("div",go,[e("label",null,n(a.$t("settings.providers.baseUrl")),1),B(e("input",{"onUpdate:modelValue":t[19]||(t[19]=S=>d.value.api_base=S),type:"text",placeholder:a.$t("chat.sessionConfig.leaveEmptyForGlobal"),class:"form-input"},null,8,_o),[[Y,d.value.api_base]]),e("p",yo,n(a.$t("chat.sessionConfig.apiBaseHint")),1)]),e("div",bo,[e("button",{onClick:Z,class:"btn-secondary",disabled:oe.value},[(s(),h($(oe.value?v(_t):v(je)),{size:16,class:ee({spin:oe.value})},null,8,["class"])),e("span",null,n(oe.value?a.$t("settings.providers.testing"):a.$t("settings.providers.testConnection")),1)],8,ho)]),g.value?(s(),u("div",{key:0,class:ee(["test-result",g.value.success?"success":"error"])},[(s(),h($(g.value.success?v(je):v(yt)),{size:16})),e("span",null,n(g.value.message),1)],2)):z("",!0)])])])):(s(),u("div",ko,[(s(),h($(v(bt)),{size:32,class:"empty-icon"})),t[50]||(t[50]=e("div",{class:"empty-text"},[e("h4",null,"使用全局默认配置"),e("p",null,"启用自定义配置以为此团队设置专属的模型和 API")],-1))]))],512)),[[Re,N.value==="model"]]):z("",!0)])])]}),_:1},8,["model-value"]),H(v(be),{"model-value":E.value,title:b.value===null?"添加成员":"编辑成员",size:"large",onClose:r},{footer:ae(()=>[e("button",{class:"co-btn co-btn--secondary",onClick:r},"取消"),e("button",{class:"co-btn co-btn--primary",onClick:C,disabled:!ne.value},"保存",8,Jo)]),default:ae(()=>[e("div",$o,[e("div",wo,[t[51]||(t[51]=e("label",null,[L("成员 ID "),e("span",{class:"required"},"*")],-1)),B(e("input",{"onUpdate:modelValue":t[20]||(t[20]=l=>c.value.id=l),type:"text",class:"form-input",placeholder:"例如：analyst"},null,512),[[Y,c.value.id]]),t[52]||(t[52]=e("p",{class:"form-hint"},"唯一标识符，用于依赖关系引用",-1))]),y.team.mode==="council"?(s(),u("div",Co,[t[53]||(t[53]=e("label",null,[L("视角 (Perspective) "),e("span",{class:"required"},"*")],-1)),B(e("input",{"onUpdate:modelValue":t[21]||(t[21]=l=>c.value.perspective=l),type:"text",class:"form-input",placeholder:"例如：技术架构师，关注可扩展性"},null,512),[[Y,c.value.perspective]]),t[54]||(t[54]=e("p",{class:"form-hint"},"描述这个成员的分析视角",-1))])):(s(),u("div",zo,[t[55]||(t[55]=e("label",null,[L("角色 (Role) "),e("span",{class:"required"},"*")],-1)),B(e("input",{"onUpdate:modelValue":t[22]||(t[22]=l=>c.value.role=l),type:"text",class:"form-input",placeholder:"例如：需求分析师"},null,512),[[Y,c.value.role]])])),y.team.mode!=="council"?(s(),u("div",So,[t[56]||(t[56]=e("label",null,"任务 (Task)",-1)),B(e("textarea",{"onUpdate:modelValue":t[23]||(t[23]=l=>c.value.task=l),class:"form-textarea",rows:"3",placeholder:"描述这个成员的具体任务..."},null,512),[[Y,c.value.task]]),t[57]||(t[57]=e("p",{class:"form-hint"},"`task` 会作为实际执行任务传给子 Agent；如果未填写系统提示词，系统也会基于角色和任务自动生成默认系统提示。",-1))])):z("",!0),y.team.mode==="graph"?(s(),u("div",xo,[t[58]||(t[58]=e("label",null,"依赖 (Depends On)",-1)),e("div",Vo,[ie().length>0?(s(),u("div",Mo,[(s(!0),u(te,null,se(ie(),l=>(s(),u("span",{key:l,class:"dependency-tag"},[L(n(l)+" ",1),e("button",{type:"button",class:"tag-remove",onClick:_=>o(l)},"×",8,To)]))),128))])):z("",!0),e("select",{class:"form-select",onChange:t[24]||(t[24]=l=>ze(l)),disabled:re().length===0},[e("option",Do,n(re().length===0?"没有可选的依赖节点":"选择依赖节点..."),1),(s(!0),u(te,null,se(re(),l=>(s(),u("option",{key:l.id,value:l.id},n(l.id)+" - "+n(l.role||l.perspective||"未命名"),9,Ao))),128))],40,Uo)]),t[59]||(t[59]=e("p",{class:"form-hint"},"选择此成员需要等待哪些成员完成后才能执行",-1))])):z("",!0),y.team.mode==="graph"?(s(),u("div",Eo,[t[68]||(t[68]=e("label",null,"执行条件（可选）",-1)),c.value.depends_on_str.trim()?(s(),u("div",Lo,[e("div",Po,[t[61]||(t[61]=e("div",{class:"toggle-content"},[e("span",{class:"toggle-title"},"启用条件执行"),e("p",{class:"toggle-hint"},"根据依赖节点的输出决定是否执行此节点")],-1)),H(pe,{modelValue:c.value.enable_condition,"onUpdate:modelValue":t[25]||(t[25]=l=>c.value.enable_condition=l),width:44,height:24,"aria-label":"启用条件执行"},null,8,["modelValue"])]),c.value.enable_condition?(s(),u("div",No,[e("div",Oo,[e("div",Ro,[t[63]||(t[63]=e("label",null,"条件类型",-1)),B(e("select",{"onUpdate:modelValue":t[26]||(t[26]=l=>c.value.condition_type=l),class:"form-select"},[...t[62]||(t[62]=[e("option",{value:"output_contains"},"输出包含",-1),e("option",{value:"output_not_contains"},"输出不包含",-1)])],512),[[ge,c.value.condition_type]])]),e("div",jo,[t[65]||(t[65]=e("label",null,"检查节点",-1)),B(e("select",{"onUpdate:modelValue":t[27]||(t[27]=l=>c.value.condition_node=l),class:"form-select"},[t[64]||(t[64]=e("option",{value:""},"选择节点...",-1)),(s(!0),u(te,null,se(Ce(),l=>{var _,q;return s(),u("option",{key:l,value:l},n(l)+" - "+n(((_=_e(l))==null?void 0:_.role)||((q=_e(l))==null?void 0:q.perspective)||"未命名"),9,qo)}),128))],512),[[ge,c.value.condition_node]]),t[66]||(t[66]=e("p",{class:"form-hint"},"可以选择任何上游节点（包括间接依赖）",-1))])]),e("div",Fo,[e("div",Ho,[t[67]||(t[67]=e("label",null,"匹配文本",-1)),B(e("input",{"onUpdate:modelValue":t[28]||(t[28]=l=>c.value.condition_text=l),type:"text",class:"form-input",placeholder:"例如：测试通过、成功、无问题"},null,512),[[Y,c.value.condition_text]]),e("p",Io,n(c.value.condition_type==="output_contains"?"当依赖节点输出包含此文本时，执行当前节点":"当依赖节点输出不包含此文本时，执行当前节点"),1)])])])):z("",!0)])):(s(),u("div",Bo,[(s(),h($(v(Oe)),{size:16})),t[60]||(t[60]=e("span",null,"请先选择依赖节点，然后可以配置基于依赖输出的执行条件",-1))]))])):z("",!0),e("div",Go,[t[69]||(t[69]=e("label",null,"系统提示词 (System Prompt)",-1)),B(e("textarea",{"onUpdate:modelValue":t[29]||(t[29]=l=>c.value.system_prompt=l),class:"form-textarea prompt-textarea",rows:"8",placeholder:`为这个智能体定义持久的系统级指令，例如：

你是一位资深的技术架构师，拥有15年的大型系统设计经验。你的职责是：
1. 评估技术方案的可行性和可扩展性
2. 识别潜在的技术风险和瓶颈
3. 提供具体的技术建议和最佳实践

请始终保持专业、客观，并提供可操作的建议。`},null,512),[[Y,c.value.system_prompt]]),t[70]||(t[70]=e("p",{class:"form-hint"}," `system_prompt` 会直接作为系统消息注入；如果这里留空，系统会自动用角色和任务生成默认系统提示。填写后会覆盖默认系统提示，但不会替代上面的 `task`。 ",-1))])])]),_:1},8,["model-value","title"])]))}}),Xo=ke(Wo,[["__scopeId","data-v-abf0ed89"]]),He=[{id:"document-analysis-pipeline",name:"文档深度分析",description:"理解文档 → 提取要点 → 分析问题 → 生成总结报告",category:"文档处理",mode:"pipeline",cross_review:!1,enable_skills:!0,agents:[{id:"reader",role:"文档理解专家",task:"通读文档，理解整体结构和核心内容",system_prompt:`你是文档理解专家，擅长快速把握文档的核心内容和结构。

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

在交叉评审中，请从受众角度评估其他人的修改建议`}]}],Ko=["全部","文档处理","内容创作","软件开发","问题诊断","决策支持"],Yo={class:"multiagent-config"},Qo={class:"teams-list-view"},Zo={class:"team-toolbar"},el={class:"team-stats"},tl={class:"team-stat"},sl={class:"team-stat"},ol={class:"team-actions"},ll=["disabled"],al={key:0,class:"team-filters"},nl={class:"team-search"},il=["placeholder"],rl={value:""},dl={value:""},ul={key:1,class:"team-state"},cl={key:2,class:"team-state"},ml={class:"team-state-desc"},pl={key:3,class:"team-empty"},vl={class:"team-empty-icon"},fl={class:"team-empty-title"},gl={class:"team-empty-desc"},_l={class:"team-empty-actions"},yl={key:4,class:"team-list"},bl=["onClick"],hl={class:"team-index"},kl={class:"team-name-line"},$l={class:"team-name"},wl={class:"team-badge"},Cl={key:0,class:"team-badge"},zl={key:1,class:"team-badge team-badge--muted"},Sl={class:"team-member-count"},xl={class:"team-row-actions"},Vl=["title","onClick"],Ml=["title","onClick"],Tl={key:5,class:"team-state"},Ul={class:"team-state-title"},Dl={class:"team-state-desc"},Al={class:"dialog-content"},El={class:"template-categories"},Bl=["onClick"],Ll={class:"templates-grid"},Pl=["onClick"],Nl={class:"template-header"},Ol={class:"template-badge"},Rl={class:"template-description"},jl={class:"template-footer"},ql={class:"template-agents"},Fl={class:"template-category"},Hl={class:"agent-form"},Il={class:"af-field"},Gl={class:"af-label",for:"team-form-name"},Jl=["placeholder"],Wl={class:"af-field"},Xl={class:"af-label",for:"team-form-desc"},Kl=["placeholder"],Yl={class:"af-field"},Ql={class:"af-label"},Zl={class:"mode-selector"},ea=["onUpdate:modelValue","value"],ta={class:"mode-content"},sa={class:"af-switches"},oa={key:0,class:"af-switch-row"},la={class:"af-switch-text"},aa={class:"af-switch-title"},na={class:"af-switch-hint"},ia={class:"af-switch-row"},ra={class:"af-switch-text"},da={class:"af-switch-title"},ua={class:"af-switch-hint"},ca=["disabled"],ma=he({__name:"MultiAgentConfig",setup(y){const{t:w}=Ge(),m=Ye(),R=Qe(),{confirm:A}=Ke(),V=Q(()=>m.teams),J=Q(()=>V.value.filter(o=>o.is_active).length),W=Q(()=>m.loading),O=Q(()=>m.error),T=x(!1),P=x(!1),k=x(null),le=x(),X=x(""),N=x(""),U=x(""),I=x("全部"),oe=Q(()=>I.value==="全部"?He:He.filter(o=>o.category===I.value)),g=Q(()=>{let o=V.value;if(X.value.trim()){const i=X.value.toLowerCase();o=o.filter(r=>r.name.toLowerCase().includes(i)||r.description&&r.description.toLowerCase().includes(i))}if(N.value&&(o=o.filter(i=>i.mode===N.value)),U.value){const i=U.value==="active";o=o.filter(r=>r.is_active===i)}return o}),p=()=>{X.value="",N.value="",U.value=""},M=o=>{f.value={name:o.name,description:o.description,mode:o.mode,cross_review:o.cross_review,enable_skills:o.enable_skills,agents:JSON.parse(JSON.stringify(o.agents)),is_active:!0},P.value=!1,T.value=!0},f=x({name:"",description:"",mode:"council",cross_review:!0,enable_skills:!1,agents:[],is_active:!0}),d={pipeline:"流水线",graph:"依赖图",council:"多视角"},D=[{id:"pipeline",name:"流水线 (Pipeline)",desc:"顺序执行，每步接收前序输出"},{id:"graph",name:"依赖图 (Graph)",desc:"无依赖项并行执行"},{id:"council",name:"多视角 (Council)",desc:"全员并行分析 → 交叉互评"}];Je(()=>G(this,null,function*(){yield ne()}));function F(){var o;(o=le.value)==null||o.click()}function E(){const o={version:"1.0.0",exported_at:new Date().toISOString(),teams:V.value.map(C=>({name:C.name,description:C.description||"",mode:C.mode,agents:C.agents,is_active:C.is_active,cross_review:C.cross_review,enable_skills:C.enable_skills}))},i=URL.createObjectURL(new Blob([JSON.stringify(o,null,2)],{type:"application/json"})),r=document.createElement("a");r.href=i,r.download=`agent-teams-${new Date().toISOString().slice(0,10)}.json`,r.click(),URL.revokeObjectURL(i)}function b(o){const i=String((o==null?void 0:o.name)||"").trim();if(!i)return null;const r=["pipeline","graph","council"].includes(o==null?void 0:o.mode)?o.mode:"pipeline";return{name:i,description:String((o==null?void 0:o.description)||""),mode:r,agents:(Array.isArray(o==null?void 0:o.agents)?o.agents:[]).filter(C=>C&&String(C.id||"").trim()).map(C=>{var j;return{id:String(C.id),role:String(C.role||""),system_prompt:C.system_prompt?String(C.system_prompt):null,task:String(C.task||""),perspective:C.perspective?String(C.perspective):null,depends_on:Array.isArray(C.depends_on)?C.depends_on.map(String):[],condition:(j=C.condition)!=null?j:null}}),is_active:(o==null?void 0:o.is_active)!==!1,cross_review:(o==null?void 0:o.cross_review)!==!1,enable_skills:!!(o!=null&&o.enable_skills)}}function c(o){return G(this,null,function*(){var C;const i=o.target,r=(C=i.files)==null?void 0:C[0];if(i.value="",!!r)try{const j=JSON.parse(yield r.text()),ve=Array.isArray(j)?j:j==null?void 0:j.teams;if(!Array.isArray(ve)||ve.length===0)throw new Error("文件里没有团队数据");const de=ve.map(b).filter(Boolean);if(!de.length)throw new Error("没有可导入的团队");const fe=new Set;for(const Z of de){if(fe.has(Z.name))throw new Error(`导入文件里存在重复团队名：${Z.name}`);fe.add(Z.name)}const Se=new Map(V.value.map(Z=>[Z.name,Z]));for(const Z of de){const ue=Se.get(Z.name);ue?yield m.updateTeam(ue.id,Z):yield m.createTeam(Z)}yield ne(),R.success(`已导入 ${de.length} 个团队`)}catch(j){R.error((j==null?void 0:j.message)||"导入失败")}})}const ne=()=>G(this,null,function*(){yield m.loadTeams()}),$e=o=>{k.value=o},we=o=>{o||(k.value=null)},Ce=()=>G(this,null,function*(){if(yield m.loadTeams(),k.value){const o=V.value.find(i=>i.id===k.value.id);o&&(k.value=o)}}),_e=o=>G(this,null,function*(){yield A({title:w("common.confirmDelete"),message:w("settings.multiagent.confirmDelete",{name:o.name}),type:"danger",confirmText:w("common.delete"),confirmVariant:"danger",onConfirm:()=>G(this,null,function*(){try{yield m.deleteTeam(o.id),R.success(w("common.success"))}catch(i){R.error(i.message||w("common.error"))}})})}),ie=o=>{const i={mode:o.mode,goal:"在这里描述你的目标...",cross_review:o.cross_review,agents:o.agents.map(r=>({id:r.id,role:r.role,perspective:r.perspective,task:r.task,depends_on:r.depends_on,system_prompt:r.system_prompt}))};navigator.clipboard.writeText(JSON.stringify(i,null,2)),R.success(w("common.copied"))},re=()=>{T.value=!1,f.value={name:"",description:"",mode:"council",cross_review:!0,enable_skills:!1,agents:[],is_active:!0}},ze=()=>G(this,null,function*(){if(!f.value.name.trim()){R.error(w("settings.multiagent.form.nameRequired"));return}try{const o=yield m.createTeam(f.value);R.success(w("settings.multiagent.form.createSuccess")),re(),k.value=o}catch(o){R.error(o.message||w("settings.multiagent.form.createError"))}});return(o,i)=>(s(),u("div",Yo,[e("div",Qo,[e("div",Zo,[e("div",el,[e("span",tl,[e("b",null,n(J.value),1),L(" "+n(o.$t("settings.multiagent.activeCount")),1)]),i[14]||(i[14]=e("span",{class:"team-stat-sep","aria-hidden":"true"},null,-1)),e("span",sl,[L(n(o.$t("settings.multiagent.totalCount"))+" ",1),e("b",null,n(V.value.length),1)])]),e("div",ol,[e("button",{class:"co-btn co-btn--secondary",onClick:F},[(s(),h($(v(ht)),{size:14})),i[15]||(i[15]=L(" 导入 ",-1))]),e("button",{class:"co-btn co-btn--secondary",disabled:!V.value.length,onClick:E},[(s(),h($(v(kt)),{size:14})),i[16]||(i[16]=L(" 导出 ",-1))],8,ll),e("button",{class:"co-btn co-btn--secondary",onClick:i[0]||(i[0]=r=>P.value=!0)},[(s(),h($(v(qe)),{size:14})),L(" "+n(o.$t("settings.multiagent.fromTemplate")),1)]),e("button",{class:"co-btn co-btn--primary",onClick:i[1]||(i[1]=r=>T.value=!0)},[(s(),h($(v(We)),{size:14})),L(" "+n(o.$t("settings.multiagent.newTeam")),1)]),e("input",{ref_key:"importInput",ref:le,type:"file",accept:"application/json,.json",class:"import-file-input",onChange:c},null,544)])]),V.value.length>0?(s(),u("div",al,[e("div",nl,[(s(),h($(v(Fe)),{size:14,class:"team-search-icon"})),B(e("input",{"onUpdate:modelValue":i[2]||(i[2]=r=>X.value=r),class:"team-search-input",type:"text",placeholder:o.$t("settings.multiagent.searchPlaceholder")},null,8,il),[[Y,X.value]]),X.value?(s(),u("button",{key:0,class:"team-search-clear",onClick:i[3]||(i[3]=r=>X.value="")},[(s(),h($(v(Ie)),{size:13}))])):z("",!0)]),B(e("select",{"onUpdate:modelValue":i[4]||(i[4]=r=>N.value=r),class:"co-select team-filter"},[e("option",rl,n(o.$t("settings.multiagent.allModes")),1),i[17]||(i[17]=e("option",{value:"pipeline"},"流水线",-1)),i[18]||(i[18]=e("option",{value:"graph"},"依赖图",-1)),i[19]||(i[19]=e("option",{value:"council"},"多视角",-1))],512),[[ge,N.value]]),B(e("select",{"onUpdate:modelValue":i[5]||(i[5]=r=>U.value=r),class:"co-select team-filter"},[e("option",dl,n(o.$t("settings.multiagent.allStatus")),1),i[20]||(i[20]=e("option",{value:"active"},"已激活",-1)),i[21]||(i[21]=e("option",{value:"inactive"},"未激活",-1))],512),[[ge,U.value]])])):z("",!0),W.value?(s(),u("div",ul,[H(v(Ut))])):O.value?(s(),u("div",cl,[e("p",ml,n(O.value),1),e("button",{class:"co-btn co-btn--secondary",onClick:ne},n(o.$t("common.retry")),1)])):V.value.length===0?(s(),u("div",pl,[e("div",vl,[(s(),h($(v(ye)),{size:22}))]),e("h3",fl,n(o.$t("settings.multiagent.empty")),1),e("p",gl,n(o.$t("settings.multiagent.emptyDesc")),1),e("div",_l,[e("button",{class:"co-btn co-btn--secondary",onClick:i[6]||(i[6]=r=>P.value=!0)},[(s(),h($(v(qe)),{size:14})),L(" "+n(o.$t("settings.multiagent.fromTemplate")),1)]),e("button",{class:"co-btn co-btn--primary",onClick:i[7]||(i[7]=r=>T.value=!0)},n(o.$t("settings.multiagent.newTeam")),1)])])):g.value.length>0?(s(),u("div",yl,[(s(!0),u(te,null,se(g.value,(r,C)=>(s(),u("div",{key:r.id,class:ee(["team-row",{"is-inactive":!r.is_active}]),onClick:j=>$e(r)},[e("span",hl,n(String(C+1).padStart(2,"0")),1),e("div",kl,[e("span",$l,n(r.name),1),e("span",wl,n(d[r.mode]),1),r.mode==="council"?(s(),u("span",Cl,n(r.cross_review?"交叉模式":"独立模式"),1)):z("",!0),r.is_active?z("",!0):(s(),u("span",zl,"未启用"))]),e("span",Sl,[(s(),h($(v(ye)),{size:12})),L(" "+n(r.agents.length)+" "+n(o.$t("settings.multiagent.agentUnit")),1)]),e("div",xl,[e("button",{class:"icon-btn",title:o.$t("settings.multiagent.copyPayload"),onClick:Ae(j=>ie(r),["stop"])},[(s(),h($(v($t)),{size:15}))],8,Vl),e("button",{class:"icon-btn icon-btn--danger",title:o.$t("common.delete"),onClick:Ae(j=>_e(r),["stop"])},[(s(),h($(v(Xe)),{size:15}))],8,Ml)]),(s(),h($(v(wt)),{size:15,class:"team-chevron"}))],10,bl))),128))])):(s(),u("div",Tl,[(s(),h($(v(Fe)),{size:22,class:"team-state-icon"})),e("p",Ul,n(o.$t("settings.multiagent.noResults")),1),e("p",Dl,n(o.$t("settings.multiagent.noResultsDesc")),1),e("button",{class:"co-btn co-btn--secondary",onClick:p},n(o.$t("settings.multiagent.clearFilters")),1)])),H(v(be),{"model-value":P.value,onClose:i[8]||(i[8]=r=>P.value=!1),size:"large"},{default:ae(()=>[e("div",Al,[i[22]||(i[22]=e("h3",null,"从模板创建团队",-1)),i[23]||(i[23]=e("p",{class:"template-hint"},"选择一个预定义模板快速创建团队，您可以在创建后修改配置",-1)),e("div",El,[(s(!0),u(te,null,se(v(Ko),r=>(s(),u("button",{key:r,class:ee(["category-btn",{active:I.value===r}]),onClick:C=>I.value=r},n(r),11,Bl))),128))]),e("div",Ll,[(s(!0),u(te,null,se(oe.value,r=>(s(),u("div",{key:r.id,class:"template-card",onClick:C=>M(r)},[e("div",Nl,[e("h4",null,n(r.name),1),e("span",Ol,n(d[r.mode]),1)]),e("p",Rl,n(r.description),1),e("div",jl,[e("span",ql,[(s(),h($(v(ye)),{size:14})),L(" "+n(r.agents.length)+" 个成员 ",1)]),e("span",Fl,n(r.category),1)])],8,Pl))),128))])])]),_:1},8,["model-value"]),H(v(be),{"model-value":T.value,title:o.$t("settings.multiagent.form.createTitle"),size:"medium",onClose:re},{footer:ae(()=>[e("button",{class:"co-btn co-btn--secondary",onClick:re},n(o.$t("common.cancel")),1),e("button",{class:"co-btn co-btn--primary",disabled:!f.value.name.trim(),onClick:ze},n(o.$t("settings.multiagent.form.createAndAddMembers")),9,ca)]),default:ae(()=>[e("div",Hl,[e("div",Il,[e("label",Gl,[L(n(o.$t("settings.multiagent.form.name"))+" ",1),i[24]||(i[24]=e("span",{class:"af-required"},"*",-1))]),B(e("input",{id:"team-form-name","onUpdate:modelValue":i[9]||(i[9]=r=>f.value.name=r),type:"text",class:"co-input",placeholder:o.$t("settings.multiagent.form.namePlaceholder")},null,8,Jl),[[Y,f.value.name]])]),e("div",Wl,[e("label",Xl,n(o.$t("settings.multiagent.form.description")),1),B(e("textarea",{id:"team-form-desc","onUpdate:modelValue":i[10]||(i[10]=r=>f.value.description=r),class:"co-textarea",rows:"3",placeholder:o.$t("settings.multiagent.form.descriptionPlaceholder")},null,8,Kl),[[Y,f.value.description]])]),e("div",Yl,[e("span",Ql,[L(n(o.$t("settings.multiagent.form.mode"))+" ",1),i[25]||(i[25]=e("span",{class:"af-required"},"*",-1))]),e("div",Zl,[(s(),u(te,null,se(D,r=>e("label",{key:r.id,class:ee(["mode-option",{selected:f.value.mode===r.id}])},[B(e("input",{"onUpdate:modelValue":C=>f.value.mode=C,type:"radio",value:r.id,class:"mode-input"},null,8,ea),[[Ct,f.value.mode]]),i[26]||(i[26]=e("span",{class:"mode-radio","aria-hidden":"true"},null,-1)),e("span",ta,[e("strong",null,n(r.name),1),e("span",null,n(r.desc),1)])],2)),64))])]),e("div",sa,[f.value.mode==="council"?(s(),u("div",oa,[e("div",la,[e("span",aa,n(o.$t("settings.multiagent.form.crossReview")),1),e("span",na,n(o.$t("settings.multiagent.form.crossReviewHint")),1)]),H(pe,{modelValue:f.value.cross_review,"onUpdate:modelValue":i[11]||(i[11]=r=>f.value.cross_review=r),width:40,height:22,"aria-label":o.$t("settings.multiagent.form.crossReview")},null,8,["modelValue","aria-label"])])):z("",!0),e("div",ia,[e("div",ra,[e("span",da,n(o.$t("settings.multiagent.form.enableSkills")),1),e("span",ua,n(o.$t("settings.multiagent.form.enableSkillsHint")),1)]),H(pe,{modelValue:f.value.enable_skills,"onUpdate:modelValue":i[12]||(i[12]=r=>f.value.enable_skills=r),width:40,height:22,"aria-label":o.$t("settings.multiagent.form.enableSkills")},null,8,["modelValue","aria-label"])])])])]),_:1},8,["model-value","title"])]),H(v(Ht),{"model-value":!!k.value,size:"wide","show-header":!1,"mask-closable":!0,"onUpdate:modelValue":we},{default:ae(()=>[k.value?(s(),h(Xo,{key:0,team:k.value,onBack:i[13]||(i[13]=r=>k.value=null),onUpdated:Ce},null,8,["team"])):z("",!0)]),_:1},8,["model-value"])]))}}),ha=ke(ma,[["__scopeId","data-v-84fa2bf4"]]);export{ha as default};
