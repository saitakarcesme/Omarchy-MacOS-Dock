.pragma library

// A continuous lens expands the neighbourhood AND displaces its neighbours.
// Resolve the pointer in the unexpanded strip to avoid hover/layout feedback.
function layout(count, pitch, base, peak, pointer, center, amount) {
    const width = count * pitch;
    const radius = pitch * 2.7;
    const amplitude = (peak-base) * amount;
    const a = amplitude/pitch;
    function integral(d) {
        if (d <= -radius) return 0;
        if (d >= radius) return radius;
        return (d+radius)/2 + radius*Math.sin(Math.PI*d/radius)/(2*Math.PI);
    }
    function extra(p) { return a*(integral(width-p)-integral(-p)); }
    function screenPointer(p) {
        return center-width/2-extra(p)/2+p+a*(integral(0)-integral(-p));
    }
    let lo = -radius*2, hi = width+radius*2;
    for (let i=0;i<32;i++) {
        const mid=(lo+hi)/2;
        if (screenPointer(mid)<pointer) lo=mid; else hi=mid;
    }
    const p=(lo+hi)/2;
    const total=width+extra(p), left=center-total/2;
    function edge(x) { return left+x+a*(integral(x-p)-integral(-p)); }
    const items=[];
    for(let i=0;i<count;i++) {
        const distance=Math.abs((i+.5)*pitch-p);
        const influence=distance>=radius?0:(1+Math.cos(Math.PI*distance/radius))/2;
        const x=edge(i*pitch), right=edge((i+1)*pitch);
        items.push({x:x,width:right-x,center:(x+right)/2,size:base+amplitude*influence});
    }
    return {left:left,width:total,items:items,virtualPointer:p};
}
