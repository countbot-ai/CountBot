var F=Object.defineProperty;var b=Object.getOwnPropertySymbols;var _=Object.prototype.hasOwnProperty,D=Object.prototype.propertyIsEnumerable;var M=(a,t,e)=>t in a?F(a,t,{enumerable:!0,configurable:!0,writable:!0,value:e}):a[t]=e,C=(a,t)=>{for(var e in t||(t={}))_.call(t,e)&&M(a,e,t[e]);if(b)for(var e of b(t))D.call(t,e)&&M(a,e,t[e]);return a};var A=(a,t,e)=>new Promise((r,s)=>{var n=i=>{try{o(e.next(i))}catch(d){s(d)}},l=i=>{try{o(e.throw(i))}catch(d){s(d)}},o=i=>i.done?r(i.value):Promise.resolve(i.value).then(n,l);o((e=e.apply(a,t)).next())});import{s as z,g as G,q as P,p as W,a as B,b as V,_ as c,I as H,z as j,E as w,F as q,G as L,l as K,K as N,e as U}from"./mermaid.core-CrhX2ate.js";import{p as X}from"./chunk-4BX2VUAB-Bnb0fCDc.js";import{p as Y}from"./treemap-KZPCXAKY-_0iYg5Va.js";import"./index-2z2G9bZP.js";import"./_baseUniq-CQWan3bt.js";import"./_basePickBy-Y2Zv9QA3.js";import"./clone-PlnfvyDi.js";var h={showLegend:!0,ticks:5,max:null,min:0,graticule:"circle"},T={axes:[],curves:[],options:h},x=structuredClone(T),Z=q.radar,J=c(()=>w(C(C({},Z),L().radar)),"getConfig"),S=c(()=>x.axes,"getAxes"),Q=c(()=>x.curves,"getCurves"),tt=c(()=>x.options,"getOptions"),et=c(a=>{x.axes=a.map(t=>{var e;return{name:t.name,label:(e=t.label)!=null?e:t.name}})},"setAxes"),at=c(a=>{x.curves=a.map(t=>{var e;return{name:t.name,label:(e=t.label)!=null?e:t.name,entries:rt(t.entries)}})},"setCurves"),rt=c(a=>{if(a[0].axis==null)return a.map(e=>e.value);const t=S();if(t.length===0)throw new Error("Axes must be populated before curves for reference entries");return t.map(e=>{const r=a.find(s=>{var n;return((n=s.axis)==null?void 0:n.$refText)===e.name});if(r===void 0)throw new Error("Missing entry for axis "+e.label);return r.value})},"computeCurveEntries"),st=c(a=>{var e,r,s,n,l,o,i,d,u,p;const t=a.reduce((g,m)=>(g[m.name]=m,g),{});x.options={showLegend:(r=(e=t.showLegend)==null?void 0:e.value)!=null?r:h.showLegend,ticks:(n=(s=t.ticks)==null?void 0:s.value)!=null?n:h.ticks,max:(o=(l=t.max)==null?void 0:l.value)!=null?o:h.max,min:(d=(i=t.min)==null?void 0:i.value)!=null?d:h.min,graticule:(p=(u=t.graticule)==null?void 0:u.value)!=null?p:h.graticule}},"setOptions"),nt=c(()=>{j(),x=structuredClone(T)},"clear"),f={getAxes:S,getCurves:Q,getOptions:tt,setAxes:et,setCurves:at,setOptions:st,getConfig:J,clear:nt,setAccTitle:V,getAccTitle:B,setDiagramTitle:W,getDiagramTitle:P,getAccDescription:G,setAccDescription:z},ot=c(a=>{X(a,f);const{axes:t,curves:e,options:r}=a;f.setAxes(t),f.setCurves(e),f.setOptions(r)},"populate"),it={parse:c(a=>A(void 0,null,function*(){const t=yield Y("radar",a);K.debug(t),ot(t)}),"parse")},lt=c((a,t,e,r)=>{var $;const s=r.db,n=s.getAxes(),l=s.getCurves(),o=s.getOptions(),i=s.getConfig(),d=s.getDiagramTitle(),u=H(t),p=ct(u,i),g=($=o.max)!=null?$:Math.max(...l.map(y=>Math.max(...y.entries))),m=o.min,v=Math.min(i.width,i.height)/2;dt(p,n,v,o.ticks,o.graticule),pt(p,n,v,i),O(p,n,l,m,g,o.graticule,i),R(p,l,o.showLegend,i),p.append("text").attr("class","radarTitle").text(d).attr("x",0).attr("y",-i.height/2-i.marginTop)},"draw"),ct=c((a,t)=>{var n;const e=t.width+t.marginLeft+t.marginRight,r=t.height+t.marginTop+t.marginBottom,s={x:t.marginLeft+t.width/2,y:t.marginTop+t.height/2};return U(a,r,e,(n=t.useMaxWidth)!=null?n:!0),a.attr("viewBox",`0 0 ${e} ${r}`),a.append("g").attr("transform",`translate(${s.x}, ${s.y})`)},"drawFrame"),dt=c((a,t,e,r,s)=>{if(s==="circle")for(let n=0;n<r;n++){const l=e*(n+1)/r;a.append("circle").attr("r",l).attr("class","radarGraticule")}else if(s==="polygon"){const n=t.length;for(let l=0;l<r;l++){const o=e*(l+1)/r,i=t.map((d,u)=>{const p=2*u*Math.PI/n-Math.PI/2,g=o*Math.cos(p),m=o*Math.sin(p);return`${g},${m}`}).join(" ");a.append("polygon").attr("points",i).attr("class","radarGraticule")}}},"drawGraticule"),pt=c((a,t,e,r)=>{const s=t.length;for(let n=0;n<s;n++){const l=t[n].label,o=2*n*Math.PI/s-Math.PI/2;a.append("line").attr("x1",0).attr("y1",0).attr("x2",e*r.axisScaleFactor*Math.cos(o)).attr("y2",e*r.axisScaleFactor*Math.sin(o)).attr("class","radarAxisLine"),a.append("text").text(l).attr("x",e*r.axisLabelFactor*Math.cos(o)).attr("y",e*r.axisLabelFactor*Math.sin(o)).attr("class","radarAxisLabel")}},"drawAxes");function O(a,t,e,r,s,n,l){const o=t.length,i=Math.min(l.width,l.height)/2;e.forEach((d,u)=>{if(d.entries.length!==o)return;const p=d.entries.map((g,m)=>{const v=2*Math.PI*m/o-Math.PI/2,$=k(g,r,s,i),y=$*Math.cos(v),E=$*Math.sin(v);return{x:y,y:E}});n==="circle"?a.append("path").attr("d",I(p,l.curveTension)).attr("class",`radarCurve-${u}`):n==="polygon"&&a.append("polygon").attr("points",p.map(g=>`${g.x},${g.y}`).join(" ")).attr("class",`radarCurve-${u}`)})}c(O,"drawCurves");function k(a,t,e,r){const s=Math.min(Math.max(a,t),e);return r*(s-t)/(e-t)}c(k,"relativeRadius");function I(a,t){const e=a.length;let r=`M${a[0].x},${a[0].y}`;for(let s=0;s<e;s++){const n=a[(s-1+e)%e],l=a[s],o=a[(s+1)%e],i=a[(s+2)%e],d={x:l.x+(o.x-n.x)*t,y:l.y+(o.y-n.y)*t},u={x:o.x-(i.x-l.x)*t,y:o.y-(i.y-l.y)*t};r+=` C${d.x},${d.y} ${u.x},${u.y} ${o.x},${o.y}`}return`${r} Z`}c(I,"closedRoundCurve");function R(a,t,e,r){if(!e)return;const s=(r.width/2+r.marginRight)*3/4,n=-(r.height/2+r.marginTop)*3/4,l=20;t.forEach((o,i)=>{const d=a.append("g").attr("transform",`translate(${s}, ${n+i*l})`);d.append("rect").attr("width",12).attr("height",12).attr("class",`radarLegendBox-${i}`),d.append("text").attr("x",16).attr("y",0).attr("class","radarLegendText").text(o.label)})}c(R,"drawLegend");var ut={draw:lt},gt=c((a,t)=>{let e="";for(let r=0;r<a.THEME_COLOR_LIMIT;r++){const s=a[`cScale${r}`];e+=`
		.radarCurve-${r} {
			color: ${s};
			fill: ${s};
			fill-opacity: ${t.curveOpacity};
			stroke: ${s};
			stroke-width: ${t.curveStrokeWidth};
		}
		.radarLegendBox-${r} {
			fill: ${s};
			fill-opacity: ${t.curveOpacity};
			stroke: ${s};
		}
		`}return e},"genIndexStyles"),mt=c(a=>{const t=N(),e=L(),r=w(t,e.themeVariables),s=w(r.radar,a);return{themeVariables:r,radarOptions:s}},"buildRadarStyleOptions"),xt=c(({radar:a}={})=>{const{themeVariables:t,radarOptions:e}=mt(a);return`
	.radarTitle {
		font-size: ${t.fontSize};
		color: ${t.titleColor};
		dominant-baseline: hanging;
		text-anchor: middle;
	}
	.radarAxisLine {
		stroke: ${e.axisColor};
		stroke-width: ${e.axisStrokeWidth};
	}
	.radarAxisLabel {
		dominant-baseline: middle;
		text-anchor: middle;
		font-size: ${e.axisLabelFontSize}px;
		color: ${e.axisColor};
	}
	.radarGraticule {
		fill: ${e.graticuleColor};
		fill-opacity: ${e.graticuleOpacity};
		stroke: ${e.graticuleColor};
		stroke-width: ${e.graticuleStrokeWidth};
	}
	.radarLegendText {
		text-anchor: start;
		font-size: ${e.legendFontSize}px;
		dominant-baseline: hanging;
	}
	${gt(t,e)}
	`},"styles"),Mt={parser:it,db:f,renderer:ut,styles:xt};export{Mt as diagram};
