'use strict';
function signalLabel(t){
 if(!t||t.dbm==null)return 'Signal not reported';
 const bound=t.bound==='at_most'?'≤':t.bound==='at_least'?'≥':'≈';
 return `${bound}${t.dbm} dBm${t.stale?' · stale':''}`;
}
function signalSvg(t){
 const colors={green:'#27ae60',yellow:'#d8a318',red:'#dc4c4c',gray:'#8995a5'};
 const color=colors[t?.color]||colors.gray;
 const count=!t||t.dbm==null||t.stale?0:t.color==='green'?4:t.color==='yellow'?2:1;
 return `<g class="signal-bars" transform="translate(38,-16)" aria-label="${esc(signalLabel(t))}"><title>${esc(signalLabel(t))} · AP receive power derived from RCPI</title>${[0,1,2,3].map(i=>`<rect x="${i*6}" y="${20-(i+1)*5}" width="4" height="${(i+1)*5}" rx="1" fill="${i<count?color:'#c6cdd6'}"/>`).join('')}<text x="-38" y="66" text-anchor="middle" font-size="10" fill="${color}">${esc(signalLabel(t))}</text></g>`;
}
function signalCard(t){
 const color=['green','yellow','red'].includes(t?.color)?t.color:'gray';
 const count=!t||t.dbm==null||t.stale?0:color==='green'?4:color==='yellow'?2:1;
 return `<div class="signal-card ${color}"><div class="signal-summary"><span class="signal-meter" role="img" aria-label="${esc(signalLabel(t))}">${[0,1,2,3].map(i=>`<i class="${i<count?'on':''}"></i>`).join('')}</span><strong>${esc(signalLabel(t))}</strong></div><small>AP RX · RCPI ${t?.rcpi??'unavailable'}${t?.age_seconds!=null?' · '+esc(t.age_seconds)+'s old':''}</small><div>SNR: <strong>not reported</strong></div><small>Noise measurement unavailable; no SNR is inferred.</small>${t?.identity?`<div>${esc(t.identity.label)}${t.identity.inferred?' · inferred ('+esc(t.identity.confidence)+' confidence)':''}</div>`:''}<small>Green ≥ −67 · yellow ≥ −75 · red &lt; −75 dBm. Display thresholds, not protocol mandates.</small></div>`;
}
