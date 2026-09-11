/* Portable, offline manual structural comparison. No HTML from pasted documents is executed. */
(() => {
  'use strict';
  const COPY_SCHEMA = 'docling_poc.review_clip';
  const REVIEW_SCHEMA = 'docling_poc.manual_review';
  const labels = {title:'문서 제목',heading:'섹션 제목',paragraph:'일반 문단',list:'목록',
    table:'표',picture:'그림',page_header:'페이지 머리글',page_footer:'페이지 바닥글',
    unknown:'분류 정보 없음'};
  const evidence = {native:'네이티브 속성',markdown:'Markdown 출력',html:'HTML 출력',text:'텍스트'};
  const relations = {explicit:'명시적 관계',level_order:'수준·읽기 순서 기반 파생 관계',
    unresolved:'상위 관계 미확정',not_section:'섹션 외 요소'};
  const canonical = value => JSON.stringify(value, function(key, item) {
    return item && typeof item === 'object' && !Array.isArray(item) ?
      Object.fromEntries(Object.keys(item).sort().map(k=>[k,item[k]])):item;
  });
  const isHeading = b => ['title','heading'].includes(b.kind);
  const el = (tag, text, cls) => {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  };
  const button = (text, action) => {
    const n = el('button',text); n.type = 'button'; n.addEventListener('click',action); return n;
  };
  const describe = b => `${labels[b.kind] || b.label} · 수준 ${b.level ?? '미제공'}\n` +
    `원본 분류: ${b.label}\n` +
    `상위 경로: ${b.path.map(p => p.text).join(' > ') || '미확정 / 없음'}\n` +
    `${evidence[b.evidence] || b.evidence} · ${relations[b.relation] || b.relation}\n` +
    `${b.location || '위치 미제공'} · ${b.source_ref || b.id}` +
    (b.resource ? `\n리소스: ${b.resource}`:'');

  function validateClip(c) {
    if (!c || c.schema !== COPY_SCHEMA || c.version !== 1) throw Error('지원하지 않는 복사 형식/버전입니다.');
    if (!c.source || !['docling','tika'].includes(c.source.tool) ||
        !Number.isInteger(c.source.run) || c.source.run < 1 ||
        !['document_id','document_sha256','fingerprint'].every(k => typeof c.source[k] === 'string') ||
        !['structured','text','markdown'].includes(c.mode) ||
        !Array.isArray(c.blocks) || !c.blocks.length || c.blocks.length > 10000) {
      throw Error('복사 데이터의 출처 또는 블록 형식이 잘못되었습니다.');
    }
    for (const b of c.blocks) {
      if (!b || !['id','text','label','kind','evidence','relation'].every(k => typeof b[k] === 'string') ||
          !(b.level === null || (Number.isInteger(b.level) && b.level > 0)) ||
          !Array.isArray(b.path) || !b.path.every(p => p && typeof p.id === 'string' && typeof p.text === 'string')) {
        throw Error('블록 구조가 잘못되었습니다.');
      }
    }
    return c;
  }

  function freeBlocks(text, markdown) {
    const result = [], stack = [];
    let paragraph = [], fenced = false;
    function push(text, kind='unknown', level=null) {
      if (!text.trim()) return;
      if (kind === 'heading') while (stack.length && stack.at(-1).level >= level) stack.pop();
      const b = {id:`paste:${result.length}`,text:text.trim(),kind,label:kind,level,
        path:stack.map(b => ({id:b.id,text:b.text})),evidence:markdown?'markdown':'text',
        relation:stack.length || level === 1 ? 'level_order':'unresolved',location:'붙여넣기'};
      result.push(b); if (kind === 'heading') stack.push(b);
    }
    const flush = () => {push(paragraph.join('\n')); paragraph = [];};
    if (!markdown) {push(text); return result;}
    for (const line of text.split(/\r?\n/)) {
      if (/^\s*(```|~~~)/.test(line)) {fenced = !fenced; paragraph.push(line); continue;}
      const h = !fenced && /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line);
      if (h) {flush(); push(h[2],'heading',h[1].length);}
      else if (!fenced && paragraph.length === 1 && /^(=+|-+)\s*$/.test(line)) {
        const t = paragraph.pop(); push(t,'heading',line[0] === '=' ? 1:2);
      } else if (!line.trim() && !fenced) flush();
      else paragraph.push(line);
    }
    flush(); return result;
  }

  function differences(a,b) {
    if (!a || !b) return '상대 구간 없음 — 원본 확인 필요';
    const notes = [];
    if (a.blocks.map(b=>b.text).join('\n') !== b.blocks.map(b=>b.text).join('\n')) notes.push('텍스트 다름');
    if (a.blocks.length !== 1 || b.blocks.length !== 1) {
      notes.push('복수 블록: 내부 자동 대응 없음, 속성 목록 직접 검토'); return notes.join('\n');
    }
    const x=a.blocks[0], y=b.blocks[0];
    if ([x.kind,y.kind].includes('unknown')) notes.push('분류 정보 부족');
    else if (x.kind !== y.kind) notes.push('분류 다름');
    if (isHeading(x) || isHeading(y)) {
      if (!isHeading(x) || !isHeading(y)) notes.push('제목 여부 다름 / 수준 비교 불가');
      else if (x.level === null || y.level === null) notes.push('수준 정보 부족');
      else if (x.level !== y.level) notes.push('수준 다름');
    }
    if ([x.relation,y.relation].includes('unresolved')) notes.push('상위 관계 정보 부족');
    else if (JSON.stringify(x.path.map(p=>p.text)) !== JSON.stringify(y.path.map(p=>p.text))) {
      notes.push('상위 제목 경로 다름 (명칭 차이 포함)');
    }
    return notes.join('\n') || '제공된 비교 속성 일치 (정확도 아님)';
  }

  function validateReview(p) {
    if(!p || p.schema!==REVIEW_SCHEMA||p.version!==1||!Array.isArray(p.reviews)||
       p.reviews.length>10000 || typeof p.document_id!=='string' ||
       typeof p.document_sha256!=='string') throw Error('지원하지 않는 검토 파일 형식/버전입니다.');
    for(const r of p.reviews) {
      if(!r||!('docling' in r)||!('tika' in r)||(!r.docling&&!r.tika)||!r.expected||
         typeof r.note!=='string'||typeof r.expected.parent!=='string'||
         !(r.expected.kind===''||Object.hasOwn(labels,r.expected.kind))||
         !(r.expected.level===null||(Number.isInteger(r.expected.level)&&r.expected.level>0))) {
        throw Error('검토 행 형식이 잘못되었습니다. 기존 목록은 유지됩니다.');
      }
      for(const tool of ['docling','tika']) {
        if(r[tool]!==null && validateClip(r[tool]).source.tool!==tool)throw Error('검토 행의 도구가 다릅니다.');
      }
    }
    return p;
  }

  // The same pure comparison rules are tested with Node; the browser remains dependency-free.
  if (typeof module !== 'undefined' && module.exports) {
    module.exports={validateClip,validateReview,freeBlocks,differences,canonical}; return;
  }

  document.querySelectorAll('.structure-review').forEach(root => {
    const data = JSON.parse(root.querySelector('.structure-data').value);
    const q = s => root.querySelector(s);
    const selected = {}, inputs = {};
    let reviews = [], editing = null, dirty = false;
    const tell = s => {q('.review-message').textContent=s;};
    function source(run) {
      return {document_id:data.document_id,document_sha256:data.document_sha256,
        tool:run.tool,run:run.run,fingerprint:run.fingerprint};
    }
    function clip(run, blocks) {
      return {schema:COPY_SCHEMA,version:1,mode:'structured',source:source(run),blocks};
    }
    function provenance(c) {
      if (!c) return '';
      if (c.mode !== 'structured') return '직접 붙여넣기: 원본 블록 연결 없음';
      const runs = data.tools[c.source.tool] || [];
      const r = runs.find(r=>r.run===c.source.run && r.fingerprint===c.source.fingerprint);
      if (c.source.document_id !== data.document_id ||
          c.source.document_sha256 !== data.document_sha256 || !r) return '출처 불일치: 자동 재연결 안 함';
      const altered = c.blocks.some(b => {
        const original = r.blocks.find(x=>x.id===b.id);
        return !original || canonical(original) !== canonical(b);
      });
      return altered ? '원본 블록과 불일치: 가져온 속성 직접 검토' : `출처 확인: ${c.source.run}회차`;
    }
    function copy(run, blocks) {
      const text=JSON.stringify(clip(run,blocks),null,2);
      q('.copy-fallback').hidden=false;
      q('.copy-text').value=text;
      q('.copy-text').focus(); q('.copy-text').select();
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(()=>tell('복사했습니다. 해당 도구 칸에 붙여넣으세요.'))
          .catch(()=>tell('아래 비교용 복사 텍스트를 직접 복사하세요.'));
      } else tell('비교용 복사 텍스트를 직접 복사하세요.');
    }
    function renderTool(tool, panel) {
      const run=selected[tool];
      panel.replaceChildren(el('h4',tool.toUpperCase()));
      if (!run) {panel.append(el('p','표시할 유효 실행 없음')); return;}
      const chooser=el('select'); chooser.setAttribute('aria-label',`${tool} 구조 실행 선택`);
      for (const r of data.tools[tool]) {
        const option=el('option',`${r.run}회차 · ${r.status}`); option.value=r.run;
        option.selected=r===run; chooser.append(option);
      }
      chooser.addEventListener('change',()=>{
        selected[tool]=data.tools[tool].find(r=>r.run===Number(chooser.value)); renderTool(tool,panel);
      });
      panel.append(chooser);
      run.warnings.forEach(w=>panel.append(el('p',w,'review-message')));
      const headings=run.blocks.filter(isHeading);
      panel.append(el('p',`제목 ${headings.length}개 · 수준 미제공 ${headings.filter(b=>b.level===null).length}개`));
      const levels={}; headings.forEach(b=>{if(b.level!==null) levels[b.level]=(levels[b.level]||0)+1;});
      panel.append(el('small',Object.entries(levels).map(([l,n])=>`L${l}: ${n}개`).join(' · ')));
      const outline=el('div',undefined,'outline'), tree=el('ul');
      const nodes=new Map(), blockNodes=new Map();
      if (!headings.length) outline.append(el('p','출력에서 식별된 제목 없음'));
      for (const b of headings) {
        const li=el('li'), link=button(`${b.level===null?'수준 미제공':`L${b.level}`} ${b.text}`,()=>{
          const target=blockNodes.get(b.id); if(target) target.scrollIntoView({block:'nearest'});
        });
        li.append(link,el('small',` ${relations[b.relation]} · ${b.location || '위치 미제공'}`));
        const children=el('ul'); li.append(children); nodes.set(b.id,{li,children});
      }
      for (const b of headings) {
        const parent=nodes.get(b.parent_heading);
        (parent ? parent.children:tree).append(nodes.get(b.id).li);
      }
      outline.append(tree); panel.append(outline);
      const start=el('input'), end=el('input');
      for (const n of [start,end]) {n.type='number';n.min=1;n.max=run.blocks.length;n.value=1;}
      start.setAttribute('aria-label',`${tool} 시작 블록`); end.setAttribute('aria-label',`${tool} 끝 블록`);
      panel.append(el('span','연속 블록 범위'),start,end,button('범위 복사',()=>{
        const a=Number(start.value), b=Number(end.value);
        if (!Number.isInteger(a)||!Number.isInteger(b)||a<1||b<a||b>run.blocks.length) {
          tell('복사 범위를 확인하세요.'); return;
        } copy(run,run.blocks.slice(a-1,b));
      }));
      const body=el('div',undefined,'blocks');
      run.blocks.forEach((b,i)=>{
        const row=el('div',undefined,'block'); blockNodes.set(b.id,row);
        row.append(button('비교용 복사',()=>copy(run,[b])),el('strong',`블록 ${i+1}`),
          el('pre',b.text || '(텍스트 없음)'),el('p',describe(b),'muted')); body.append(row);
      });
      panel.append(body);
    }
    for (const tool of ['docling','tika']) {
      const runs=data.tools[tool]||[];
      selected[tool]=runs.find(r=>r.status==='success')||runs[0];
      const panel=el('div',undefined,'tool-panel'); q('.structure-tools').append(panel); renderTool(tool,panel);
      const paste=el('div'), area=el('textarea'), mode=el('select'), absent=el('input');
      area.setAttribute('aria-label',`${tool} 비교 구간`);
      area.placeholder='비교용 복사 데이터 또는 텍스트를 붙여넣으세요.';
      for (const [v,t] of [['auto','비교용 데이터 / 일반 텍스트'],['text','일반 텍스트 (JSON 해석 안 함)'],
        ['markdown','Markdown 원문 (제목 표기)']]) {
        const o=el('option',t);o.value=v;mode.append(o);
      }
      mode.setAttribute('aria-label',`${tool} 붙여넣기 형식`);
      absent.type='checkbox';const absentLabel=el('label');absentLabel.append(absent,' 상대 구간 없음');
      const preview=el('div',undefined,'preview');
      absent.addEventListener('change',()=>{area.disabled=absent.checked;refresh();});
      area.addEventListener('input',refresh);mode.addEventListener('change',refresh);
      inputs[tool]={area,mode,absent,preview};
      paste.append(el('h4',tool.toUpperCase()),mode,absentLabel,area,preview);q('.paste-grid').append(paste);
    }
    function read(tool) {
      const p=inputs[tool]; if(p.absent.checked) return null;
      const text=p.area.value.trim(); if(!text) throw Error(`${tool.toUpperCase()} 구간을 입력하세요.`);
      if(p.mode.value==='auto' && /^[\[{]/.test(text)) {
        let parsed;try{parsed=JSON.parse(text);}catch{throw Error('JSON처럼 시작하는 입력이 잘못되었습니다.');}
        const c=validateClip(parsed);
        if(c.source.tool!==tool) throw Error('도구가 다른 칸에 붙여넣었습니다.');
        return c;
      }
      const run=selected[tool];
      return {schema:COPY_SCHEMA,version:1,mode:p.mode.value==='markdown'?'markdown':'text',
        source:run?source(run):{document_id:data.document_id,document_sha256:data.document_sha256,
          tool,run:1,fingerprint:''},blocks:freeBlocks(text,p.mode.value==='markdown')};
    }
    function refresh() {
      for(const tool of ['docling','tika']) {
        if(!inputs[tool]) continue;
        try {
          const c=read(tool);
          inputs[tool].preview.textContent=c?`${provenance(c)}\n${c.blocks.length}개 블록\n`+
            c.blocks.map(b=>`${b.text}\n${describe(b)}`).join('\n\n'):'상대 구간 없음';
        } catch(e){inputs[tool].preview.textContent=e.message;}
      }
    }
    function expectedText(c,e) {
      if(!c) return '판정 불가: 상대 구간 없음';
      if(c.blocks.length!==1) return '판정 보류: 복수 블록';
      const b=c.blocks[0], out=[];
      if(e.kind) out.push(b.kind==='unknown'?'분류 정보 부족':b.kind===e.kind?'기대 분류 일치':'기대 분류 불일치');
      if(e.level!==null) out.push(b.level===null?'수준 정보 부족':b.level===e.level?'기대 수준 일치':'기대 수준 불일치');
      if(e.parent) out.push(b.relation==='unresolved'?'상위 관계 정보 부족':
        b.path.at(-1)?.text===e.parent?'기대 상위 제목 일치':'기대 상위 제목 불일치');
      return out.join(' · ') || '기대값 미지정';
    }
    function renderReviews() {
      const tbody=q('.review-table tbody');tbody.replaceChildren();
      q('.review-count').textContent=`수동 검토 ${reviews.length}쌍 (전체 정확도 아님)`;
      reviews.forEach((r,index)=>{
        const tr=el('tr');
        for(const tool of ['docling','tika']) {
          const td=el('td'), c=r[tool];
          td.append(el('p',c?provenance(c):'상대 구간 없음','muted'));
          if(c) c.blocks.forEach(b=>td.append(el('p',b.text),el('small',describe(b))));
          tr.append(td);
        }
        tr.append(el('td',differences(r.docling,r.tika)));
        tr.append(el('td',`기대 분류: ${labels[r.expected.kind]||'미지정'}\n기대 수준: ${r.expected.level??'미지정'}\n`+
          `기대 상위: ${r.expected.parent||'미지정'}\nDOCLING: ${expectedText(r.docling,r.expected)}\n`+
          `TIKA: ${expectedText(r.tika,r.expected)}\n메모: ${r.note}`));
        const actions=el('td');
        actions.append(button('수정',()=>{
          editing=index;
          for(const tool of ['docling','tika']) {
            inputs[tool].absent.checked=r[tool]===null;
            inputs[tool].area.disabled=r[tool]===null;
            inputs[tool].area.value=r[tool]?JSON.stringify(r[tool],null,2):'';
            inputs[tool].mode.value='auto';
          }
          q('.expected-kind').value=r.expected.kind;q('.expected-level').value=r.expected.level??'';
          q('.expected-parent').value=r.expected.parent;q('.review-note').value=r.note;
          q('.add-comparison').textContent='비교 수정 저장';refresh();q('.paste-grid').scrollIntoView();
        }),button('삭제',()=>{
          reviews.splice(index,1);editing=null;dirty=true;reset();renderReviews();
        }));tr.append(actions);tbody.append(tr);
      });
    }
    function reset() {
      editing=null;
      for(const p of Object.values(inputs)) {p.area.value='';p.area.disabled=false;p.absent.checked=false;}
      for(const s of ['.expected-kind','.expected-level','.expected-parent','.review-note'])q(s).value='';
      q('.add-comparison').textContent='비교 추가';refresh();
    }
    q('.reset-draft').addEventListener('click',reset);
    q('.add-comparison').addEventListener('click',()=>{
      try {
        const a=read('docling'),b=read('tika');if(!a&&!b)throw Error('적어도 한쪽 구간을 입력하세요.');
        const value=q('.expected-level').value, level=value===''?null:Number(value);
        if(level!==null && (!Number.isInteger(level)||level<1))throw Error('기대 수준은 양의 정수입니다.');
        const row={docling:a,tika:b,expected:{kind:q('.expected-kind').value,level,
          parent:q('.expected-parent').value.trim()},note:q('.review-note').value};
        if(editing===null)reviews.push(row);else reviews[editing]=row;
        dirty=true;reset();renderReviews();tell('비교를 저장했습니다. 파일로 내보내야 보존됩니다.');
      }catch(e){tell(e.message);}
    });
    q('.export-reviews').addEventListener('click',()=>{
      const payload={schema:REVIEW_SCHEMA,version:1,document_id:data.document_id,
        document_sha256:data.document_sha256,reviews};
      const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
      const a=el('a');a.href=url;a.download='manual-review.json';document.body.append(a);a.click();a.remove();
      setTimeout(()=>URL.revokeObjectURL(url),10000);dirty=false;tell('검토 JSON 다운로드를 요청했습니다.');
    });
    q('.import-reviews').addEventListener('change',async event=>{
      try {
        const file=event.target.files[0];if(!file)return;
        if(file.size>20*1024*1024)throw Error('검토 파일은 20 MB 이하로 불러오세요.');
        const p=validateReview(JSON.parse(await file.text()));
        reviews.push(...p.reviews);dirty=true;renderReviews();
        tell(p.document_id!==data.document_id||p.document_sha256!==data.document_sha256?
          '문서 불일치: 가져온 구간을 자동 재연결하지 않습니다. 출처를 확인하세요.':
          `${p.reviews.length}쌍을 추가했습니다. 각 행의 실행 출처도 확인하세요.`);
      }catch(e){tell(e.message);}finally{event.target.value='';}
    });
    window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
    renderReviews();refresh();
  });
})();
