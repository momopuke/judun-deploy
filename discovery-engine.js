/* Equal-probability method discovery. This selects a method, not a prediction. */
(function(root){'use strict';
 const ids=['western','ziwei','bazi','vedic','iching','tarotDraw','numerology','meihua','liuyao','nineStar','tarotBirth','maya'];
 const mod=(n,m)=>((n%m)+m)%m;
 function randomIndex(max=ids.length){if(!Number.isInteger(max)||max<1||max>65536)throw Error('Invalid random range');if(!root.crypto?.getRandomValues)throw Error('此瀏覽器未提供安全亂數');const limit=4294967296-(4294967296%max),a=new Uint32Array(1);do{root.crypto.getRandomValues(a)}while(a[0]>=limit);return a[0]%max;}
 function selectedAt(rotation){return Math.floor(mod(-rotation,360)/30);}
 function plan(index,start=0,turns=5,jitter=0){if(!Number.isInteger(index)||index<0||index>=12||!Number.isFinite(start)||!Number.isInteger(turns)||turns<3||!Number.isFinite(jitter)||Math.abs(jitter)>10)throw Error('Invalid wheel plan');const landing=mod(360-index*30-15+jitter,360),target=start+turns*360+mod(landing-mod(start,360),360);return {index,id:ids[index],start,target};}
 root.FateDiscovery={ids,randomIndex,plan,selectedAt};
 if(typeof module==='object'&&module.exports)module.exports=root.FateDiscovery;
})(typeof window==='object'?window:globalThis);
