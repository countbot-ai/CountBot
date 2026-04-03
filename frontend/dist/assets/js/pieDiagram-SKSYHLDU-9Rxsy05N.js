var L=(e,r,p)=>new Promise((h,i)=>{var c=a=>{try{t(p.next(a))}catch(o){i(o)}},l=a=>{try{t(p.throw(a))}catch(o){i(o)}},t=a=>a.done?h(a.value):Promise.resolve(a.value).then(c,l);t((p=p.apply(e,r)).next())});import{a4 as y,a7 as z,aJ as q,g as J,s as Z,a as H,b as K,q as Q,p as X,_ as g,l as F,c as Y,E as ee,I as te,N as ae,e as re,z as ne,F as ie}from"./mermaid.core-r8N55d0s.js";import{p as se}from"./chunk-4BX2VUAB-PZBdXpnI.js";import{p as le}from"./treemap-KZPCXAKY-C4o0F2Sa.js";import{d as W}from"./arc-fGeqUbbh.js";import{o as oe}from"./ordinal-Cboi1Yqb.js";import"./index-BXP83Zlh.js";import"./ChatWindow-gtumT3OM.js";import"./countbot-logo-CNglRKg-.js";import"./_baseUniq-CUb3D8S3.js";import"./_basePickBy-DyrnkkhQ.js";import"./clone-CEi-JaXM.js";import"./init-Gi6I4Gst.js";function ce(e,r){return r<e?-1:r>e?1:r>=e?0:NaN}function pe(e){return e}function ue(){var e=pe,r=ce,p=null,h=y(0),i=y(z),c=y(0);function l(t){var a,o=(t=q(t)).length,d,S,x=0,u=new Array(o),s=new Array(o),m=+h.apply(this,arguments),w=Math.min(z,Math.max(-z,i.apply(this,arguments)-m)),v,$=Math.min(Math.abs(w)/o,c.apply(this,arguments)),T=$*(w<0?-1:1),f;for(a=0;a<o;++a)(f=s[u[a]=a]=+e(t[a],a,t))>0&&(x+=f);for(r!=null?u.sort(function(D,C){return r(s[D],s[C])}):p!=null&&u.sort(function(D,C){return p(t[D],t[C])}),a=0,S=x?(w-o*T)/x:0;a<o;++a,m=v)d=u[a],f=s[d],v=m+(f>0?f*S:0)+T,s[d]={data:t[d],index:a,value:f,startAngle:m,endAngle:v,padAngle:$};return s}return l.value=function(t){return arguments.length?(e=typeof t=="function"?t:y(+t),l):e},l.sortValues=function(t){return arguments.length?(r=t,p=null,l):r},l.sort=function(t){return arguments.length?(p=t,r=null,l):p},l.startAngle=function(t){return arguments.length?(h=typeof t=="function"?t:y(+t),l):h},l.endAngle=function(t){return arguments.length?(i=typeof t=="function"?t:y(+t),l):i},l.padAngle=function(t){return arguments.length?(c=typeof t=="function"?t:y(+t),l):c},l}var ge=ie.pie,N={sections:new Map,showData:!1},E=N.sections,G=N.showData,de=structuredClone(ge),fe=g(()=>structuredClone(de),"getConfig"),me=g(()=>{E=new Map,G=N.showData,ne()},"clear"),he=g(({label:e,value:r})=>{if(r<0)throw new Error(`"${e}" has invalid value: ${r}. Negative values are not allowed in pie charts. All slice values must be >= 0.`);E.has(e)||(E.set(e,r),F.debug(`added new section: ${e}, with value: ${r}`))},"addSection"),ve=g(()=>E,"getSections"),xe=g(e=>{G=e},"setShowData"),ye=g(()=>G,"getShowData"),_={getConfig:fe,clear:me,setDiagramTitle:X,getDiagramTitle:Q,setAccTitle:K,getAccTitle:H,setAccDescription:Z,getAccDescription:J,addSection:he,getSections:ve,setShowData:xe,getShowData:ye},Se=g((e,r)=>{se(e,r),r.setShowData(e.showData),e.sections.map(r.addSection)},"populateDb"),we={parse:g(e=>L(void 0,null,function*(){const r=yield le("pie",e);F.debug(r),Se(r,_)}),"parse")},Ae=g(e=>`
  .pieCircle{
    stroke: ${e.pieStrokeColor};
    stroke-width : ${e.pieStrokeWidth};
    opacity : ${e.pieOpacity};
  }
  .pieOuterCircle{
    stroke: ${e.pieOuterStrokeColor};
    stroke-width: ${e.pieOuterStrokeWidth};
    fill: none;
  }
  .pieTitleText {
    text-anchor: middle;
    font-size: ${e.pieTitleTextSize};
    fill: ${e.pieTitleTextColor};
    font-family: ${e.fontFamily};
  }
  .slice {
    font-family: ${e.fontFamily};
    fill: ${e.pieSectionTextColor};
    font-size:${e.pieSectionTextSize};
    // fill: white;
  }
  .legend text {
    fill: ${e.pieLegendTextColor};
    font-family: ${e.fontFamily};
    font-size: ${e.pieLegendTextSize};
  }
`,"getStyles"),De=Ae,Ce=g(e=>{const r=[...e.values()].reduce((i,c)=>i+c,0),p=[...e.entries()].map(([i,c])=>({label:i,value:c})).filter(i=>i.value/r*100>=1).sort((i,c)=>c.value-i.value);return ue().value(i=>i.value)(p)},"createPieArcs"),$e=g((e,r,p,h)=>{F.debug(`rendering pie chart
`+e);const i=h.db,c=Y(),l=ee(i.getConfig(),c.pie),t=40,a=18,o=4,d=450,S=d,x=te(r),u=x.append("g");u.attr("transform","translate("+S/2+","+d/2+")");const{themeVariables:s}=c;let[m]=ae(s.pieOuterStrokeWidth);m!=null||(m=2);const w=l.textPosition,v=Math.min(S,d)/2-t,$=W().innerRadius(0).outerRadius(v),T=W().innerRadius(v*w).outerRadius(v*w);u.append("circle").attr("cx",0).attr("cy",0).attr("r",v+m/2).attr("class","pieOuterCircle");const f=i.getSections(),D=Ce(f),C=[s.pie1,s.pie2,s.pie3,s.pie4,s.pie5,s.pie6,s.pie7,s.pie8,s.pie9,s.pie10,s.pie11,s.pie12];let b=0;f.forEach(n=>{b+=n});const I=D.filter(n=>(n.data.value/b*100).toFixed(0)!=="0"),M=oe(C);u.selectAll("mySlices").data(I).enter().append("path").attr("d",$).attr("fill",n=>M(n.data.label)).attr("class","pieCircle"),u.selectAll("mySlices").data(I).enter().append("text").text(n=>(n.data.value/b*100).toFixed(0)+"%").attr("transform",n=>"translate("+T.centroid(n)+")").style("text-anchor","middle").attr("class","slice"),u.append("text").text(i.getDiagramTitle()).attr("x",0).attr("y",-400/2).attr("class","pieTitleText");const O=[...f.entries()].map(([n,A])=>({label:n,value:A})),k=u.selectAll(".legend").data(O).enter().append("g").attr("class","legend").attr("transform",(n,A)=>{const R=a+o,V=R*O.length/2,U=12*a,j=A*R-V;return"translate("+U+","+j+")"});k.append("rect").attr("width",a).attr("height",a).style("fill",n=>M(n.label)).style("stroke",n=>M(n.label)),k.append("text").attr("x",a+o).attr("y",a-o).text(n=>i.getShowData()?`${n.label} [${n.value}]`:n.label);const B=Math.max(...k.selectAll("text").nodes().map(n=>{var A;return(A=n==null?void 0:n.getBoundingClientRect().width)!=null?A:0})),P=S+t+a+o+B;x.attr("viewBox",`0 0 ${P} ${d}`),re(x,d,P,l.useMaxWidth)},"draw"),Te={draw:$e},We={parser:we,db:_,renderer:Te,styles:De};export{We as diagram};
