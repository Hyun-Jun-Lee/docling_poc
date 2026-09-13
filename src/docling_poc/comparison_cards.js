/* Offline sample cards. Evidence stays literal; summaries never grade extraction accuracy. */
(() => {
  'use strict';
  const SCHEMA = 'docling_poc.feature_cards';
  const MAX_CARDS = 200, MAX_CHARS = 2000000, MAX_BYTES = 20 * 1024 * 1024;
  const kinds = {headings:'제목·본문',lists:'목록·관계',formatting:'서식',tables:'표 구조',
    pictures:'그림·캡션',furniture:'본문·머리글',location:'원본 위치',other:'기타'};
  const features = {
    classification:['요소 분류','값이 있는 분류는 항목별 처리에 활용할 수 있습니다. 분류의 정답은 원본 확인이 필요합니다.'],
    headings:['제목 수준','제목 수준이 있으면 경로 구성에 활용합니다. 같은 수준만 있으면 다단계 계층 근거가 되지 않습니다.'],
    hierarchy:['그룹·관계','명시적 참조는 대상을 조회해야 합니다. 목록·제목의 의미적 소속은 원본과 대조합니다.'],
    formatting:['서식','채워진 서식 값을 직접 조회합니다. 굵기만으로 제목을 새로 분류하지 않습니다.'],
    tables:['표 구조','행·열·셀·병합 속성으로 표를 재구성할 수 있습니다. 원본 표와의 일치는 별도 확인합니다.'],
    resources:['그림·캡션','캡션·그림·주석의 참조 대상을 확인합니다. 리소스 수는 문서 요소 수와 다릅니다.'],
    location:['원본 위치','페이지·영역 값이 있으면 원본 추적에 활용합니다. 좌표가 올바른지는 원본 대조가 필요합니다.'],
    metadata:['문서·리소스 메타데이터','출처 관리에 활용합니다. 문서의 페이지 수와 요소별 위치는 구분합니다.'],
  };
  const focus = {
    headings:['classification','headings','hierarchy','location'],
    lists:['classification','hierarchy','location'],
    formatting:['classification','formatting'], tables:['tables','hierarchy','location'],
    pictures:['resources','hierarchy','location'], furniture:['classification','hierarchy','location'],
    location:['location','metadata'], other:Object.keys(features),
  };
  const owns = (o,k) => o !== null && typeof o === 'object' && Object.hasOwn(o,k);
  const object = o => o !== null && typeof o === 'object' && !Array.isArray(o);
  const blank = () => ({mode:'발췌에 없음',details:'붙여넣은 범위에서 확인할 근거가 없습니다.',
    next:'필요하면 관련 원본 항목을 추가하세요. 도구 전체의 미지원으로 판단하지 않습니다.'});
  const pretty = value => JSON.stringify(value,null,2);
  function short(value) {
    const text = pretty(value);
    return text.length > 600 ? text.slice(0,600) + '\n… (표시 생략, 아래 원본 증거 확인)' : text;
  }
  function fieldState(value) {
    if (value === null) return 'null';
    if (value === false) return 'false';
    if (value === true) return 'true';
    if (value === '') return '빈 문자열';
    if (Array.isArray(value) && !value.length) return '빈 배열';
    if (object(value) && !Object.keys(value).length) return '빈 객체';
    return '값 있음';
  }
  function fieldRows(nodes, paths) {
    const rows = [];
    for (const {source,item} of nodes) for (const path of paths) {
      let value=item, found=true;
      for (const key of path.split('.')) {
        if (!owns(value,key)) {found=false;break;}
        value=value[key];
      }
      if (found) rows.push({source,field:path,state:fieldState(value),value});
    }
    return rows;
  }
  function native(rows,key) {
    if (!rows.length) return blank();
    return {mode:'명시적 필드',
      details:rows.slice(0,6).map(r=>`${r.source} · ${r.field} (${r.state})\n${short(r.value)}`).join('\n\n') +
        (rows.length>6 ? `\n\n총 ${rows.length}개 관찰 중 6개 표시. 전체 발췌는 원본 증거에서 확인하세요.`:''),
      next:features[key][1]};
  }
  function doclingNodes(raw) {
    const doc=owns(raw,'document')?raw.document:raw;
    const nodes=[], roots=object(doc)?[{source:'문서 발췌',item:doc}]:[];
    const add=(items,collection)=>{
      if (!Array.isArray(items)||items.some(x=>!object(x))) throw Error('Docling 항목은 객체 배열이어야 합니다.');
      for (const [i,item] of items.entries()) nodes.push({
        source:typeof item.self_ref==='string'?item.self_ref:`발췌 ${collection}[${i}]`,item,collection});
    };
    if (Array.isArray(doc)) add(doc,'items');
    else if (object(doc)) {
      let collections=false;
      for (const name of ['texts','groups','tables','pictures','key_value_items','form_items']) {
        if (owns(doc,name)) {add(doc[name],name);collections=true;}
      }
      if (owns(doc,'items')) {add(doc.items,'items');collections=true;}
      if (!collections) add([doc],'items');
    } else throw Error('Docling JSON은 문서 객체, 항목 객체 또는 항목 배열이어야 합니다.');
    return {nodes,roots};
  }
  function referenceSummary(nodes) {
    const ids = new Map(), refs=[];
    for (const {item} of nodes) if (typeof item.self_ref==='string') {
      ids.set(item.self_ref,(ids.get(item.self_ref)||0)+1);
    }
    for (const {item} of nodes) for (const key of ['parent','children','captions','footnotes','references']) {
      const value=item[key];
      for (const v of (Array.isArray(value)?value:[value])) {
        if (object(v)&&typeof v.$ref==='string') refs.push(v.$ref);
      }
    }
    if (!refs.length) return '';
    const resolved=refs.filter(r=>ids.get(r)===1).length;
    return `\n\n참조 ${refs.length}개 중 발췌 내부의 유일한 대상으로 확인 ${resolved}개. `+
      `나머지 ${refs.length-resolved}개는 발췌 밖 대상 또는 중복 ID일 수 있습니다. 의미적 관계의 정답 판정은 아닙니다.`;
  }
  function doclingObservations(raw) {
    const {nodes,roots}=doclingNodes(raw);
    const fields={
      classification:['label','content_layer'],headings:['level'],
      hierarchy:['parent','children','marker','enumerated'],
      formatting:['formatting','hyperlink'],
      tables:['data.num_rows','data.num_cols','data.table_cells','data.grid'],
      resources:['captions','footnotes','references','annotations','image.mimetype'],
      location:['prov'],metadata:['origin','name'],
    };
    const result={};
    for (const key of Object.keys(features)) {
      let rows=fieldRows(key==='metadata'?roots:nodes,fields[key]);
      if (key==='hierarchy') {
        const groups=nodes.filter(n=>n.collection==='groups'||/^#\/groups\/\d+$/.test(n.item.self_ref||''));
        rows=fieldRows(groups,['label','name']).concat(rows,fieldRows(roots,['groups','body.children','furniture.children']));
      }
      result[key]=native(rows,key);
    }
    result.hierarchy.details+=referenceSummary(nodes);
    return result;
  }
  function markdownSignals(content) {
    // Deliberately a limited, disclosed syntax scan, not a CommonMark parser or semantic classifier.
    const signals={headings:[],lists:[],formatting:[],tables:[],warnings:[]};
    if (/^\s*(?:<!doctype|<(?:html|body|div|p|h[1-6]|table|ul|ol)(?:\s|>))/i.test(content)) {
      signals.warnings.push('HTML 원문은 실행·해석하지 않습니다. 원본 증거에서 직접 확인하세요.');
      return signals;
    }
    let fence=null, previous='';
    content.split(/\r\n|\n|\r/).forEach((line,index)=>{
      const marker=/^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line);
      if (fence) {
        if (marker && marker[1][0]===fence[0] && marker[1].length>=fence.length && !marker[2].trim()) fence=null;
        previous=''; return;
      }
      if (marker) {fence=marker[1];previous='';return;}
      if (/^( {4}|\t)/.test(line)) {previous='';return;}
      const cleaned=line.replace(/(`+)([\s\S]*?)\1/g,'').replace(/\\[\s\S]/g,'');
      const heading=/^ {0,3}(#{1,6})(?:[ \t]+(.*)|$)/.exec(cleaned);
      if (heading) signals.headings.push({line:index+1,level:heading[1].length,text:heading[2]||''});
      else if (previous.trim() && /^ {0,3}(=+|-+)\s*$/.test(cleaned) &&
               !/^\s*(?:[-+*]|\d+[.)])\s/.test(previous)) {
        signals.headings.push({line:index,level:cleaned.trim()[0]==='='?1:2,text:previous});
      }
      if (/^ {0,3}(?:[-+*]|\d+[.)])\s+\S/.test(cleaned)) signals.lists.push({line:index+1,text:line});
      if (/(\*\*|__)[^\n]+?\1/.test(cleaned)) signals.formatting.push({line:index+1,text:line});
      if (cleaned.includes('|')) {
        const cells=cleaned.trim().replace(/^\||\|$/g,'').split('|');
        if (cells.length>1&&cells.every(c=>/^\s*:?-{3,}:?\s*$/.test(c))&&previous.includes('|')) {
          signals.tables.push({line:index+1,columns:cells.length,header:previous});
        }
      }
      previous=cleaned;
    });
    return signals;
  }
  function markupObservations(content) {
    const signals=markdownSignals(content), result=Object.fromEntries(Object.keys(features).map(k=>[k,blank()]));
    const syntax=(items,note)=>items.length ? {mode:'출력 마크업 · 표기 후보',
      details:`${items.length}개 후보\n${short(items.slice(0,6))}`,
      next:note+' ATX/Setext 제목, 간단한 목록·굵게·파이프 표만 탐지합니다. 코드·중첩 등 전체 문법 분석은 아닙니다.'}:blank();
    result.classification=syntax([...signals.headings.map(x=>({...x,type:'제목 표기'})),
      ...signals.lists.map(x=>({...x,type:'목록 표기'})),...signals.tables.map(x=>({...x,type:'표 표기'}))],
    '마크업 해석이 필요합니다. 이미지 파일명 제목도 포함될 수 있으므로 원본과 대조하세요.');
    result.headings=syntax(signals.headings,'제목 수준·순서로 경로를 구성해야 합니다. 명시적 부모 관계는 아닙니다.');
    result.hierarchy=syntax(signals.lists,'목록 표기를 해석해 소속 구조를 구성해야 합니다. 그룹 객체를 확인한 것은 아닙니다.');
    result.formatting=syntax(signals.formatting,'Markdown 해석으로 서식 구간을 얻을 수 있습니다.');
    result.tables=syntax(signals.tables,'파이프 표 해석이 필요합니다. 병합 셀·헤더의 원본 관계는 별도로 확인하세요.');
    if (signals.warnings.length) for (const value of Object.values(result)) {
      value.mode='판단 불가';value.details=signals.warnings.join('\n');
    }
    return result;
  }
  function analyzeEvidence(tool,evidence) {
    if (evidence===null) return Object.fromEntries(Object.keys(features).map(k=>[k,{
      mode:'증거 미입력',details:'이 도구의 비교 구간을 입력하지 않았습니다.',next:'누락 오류 또는 기능 미지원으로 판단하지 않습니다.'}]));
    if (evidence.format==='text') return Object.fromEntries(Object.keys(features).map(k=>[k,{
      mode:'판단 불가',details:'일반 텍스트 입력입니다. 구조·서식 속성을 판정하지 않습니다.',next:'원본 증거를 직접 비교하거나 JSON·Markdown 원문을 추가하세요.'}]));
    if (evidence.format==='markdown') return markupObservations(evidence.content);
    const raw=JSON.parse(evidence.content);
    if (tool==='docling') return doclingObservations(raw);
    const resources=Array.isArray(raw)?raw:[raw];
    if (resources.some(r=>!object(r))) throw Error('Tika JSON은 리소스 객체 또는 객체 배열이어야 합니다.');
    const result=Object.fromEntries(Object.keys(features).map(k=>[k,blank()]));
    const nativeRows=[];
    for (const [index,item] of resources.entries()) {
      const key=owns(item,'tk:content')?'tk:content':owns(item,'X-TIKA:content')?'X-TIKA:content':null;
      if (key) {
        if (typeof item[key]!=='string') throw Error('Tika 내용 필드는 문자열이어야 합니다.');
        const observations=markupObservations(item[key]);
        for (const name of Object.keys(features)) if (observations[name].mode!=='발췌에 없음') {
          if (result[name].mode==='발췌에 없음') result[name]={...observations[name],details:''};
          result[name].details+=`발췌 리소스[${index}] · ${key}\n${observations[name].details}\n\n`;
        }
      }
      nativeRows.push(...Object.keys(item).filter(k=>k!=='tk:content'&&k!=='X-TIKA:content').map(key=>({
        source:`발췌 리소스[${index}]`,field:key,state:fieldState(item[key]),value:item[key]})));
    }
    result.metadata=native(nativeRows,'metadata');
    const resourceRows=nativeRows.filter(r=>/resource|embedded|Content-Type/i.test(r.field));
    result.resources=native(resourceRows,'resources');
    if (resourceRows.length) result.resources.next+=' 내장 리소스 깊이는 본문 목록·제목 계층이 아닙니다.';
    result.location={mode:'판단 불가',details:'Tika JSON의 요소별 위치는 자동 판정하지 않습니다. 메타데이터·원본 증거를 확인하세요.',
      next:'리소스 이름·페이지 수를 요소별 좌표로 해석하지 않습니다. 실제 위치 속성이 있으면 검토 메모에 기록하세요.'};
    return result;
  }
  function validateBundle(payload,documents) {
    if (!object(payload)||payload.schema!==SCHEMA||payload.version!==1||
        !Array.isArray(payload.cards)||payload.cards.length>MAX_CARDS) throw Error('카드 schema/version 또는 cards 배열을 확인하세요.');
    if(new TextEncoder().encode(pretty(payload)).length>MAX_BYTES)throw Error('카드 JSON은 20 MB 이하로 보관하세요.');
    const seen=new Set();
    for (const c of payload.cards) {
      if (!object(c)||!['id','document_id','document_sha256','title','kind','reason','source_location','note']
        .every(k=>typeof c[k]==='string')||!c.id.trim()||!c.title.trim()||!owns(kinds,c.kind)) {
        throw Error('카드 ID·제목·유형과 필수 문자열을 확인하세요.');
      }
      if (seen.has(c.id)) throw Error(`중복 카드 ID: ${c.id}`);seen.add(c.id);
      const doc=documents.find(d=>d.id===c.document_id&&d.sha256===c.document_sha256);
      if (!doc) throw Error(`카드 ${c.id}: 문서 ID 또는 SHA-256이 보고서와 다릅니다.`);
      if (c.original_checked!=null&&typeof c.original_checked!=='boolean') throw Error('original_checked 값을 확인하세요.');
      if (c.docling==null&&c.tika==null) throw Error('적어도 한 도구의 증거가 필요합니다.');
      for (const tool of ['docling','tika']) {
        const e=c[tool];if (e==null) continue;
        if (!object(e)||!['json','markdown','text'].includes(e.format)||typeof e.content!=='string'||
          !e.content.trim()||(e.content.length>MAX_CHARS&&Array.from(e.content).length>MAX_CHARS)||typeof e.source_file!=='string'||
          !Array.isArray(e.source_refs)||!e.source_refs.every(r=>typeof r==='string')) {
          throw Error(`${tool}: 입력 형식·원문·출처를 확인하세요. 원문은 200만 자 이하입니다.`);
        }
        if (e.run!=null&&(!Number.isInteger(e.run)||e.run<1||!doc.runs[tool].some(r=>r.number===e.run))) {
          throw Error(`${tool}: 보고서에 없는 회차입니다.`);
        }
        if (e.format==='json') {
          let raw;try {raw=JSON.parse(e.content);} catch {throw Error(`${tool}: 원문 JSON 문법을 확인하세요.`);}
          if (!object(raw)&&!Array.isArray(raw)) throw Error(`${tool}: JSON 증거는 객체 또는 배열이어야 합니다.`);
        }
        analyzeEvidence(tool,e);
      }
    }
    return payload.cards;
  }
  function mergeCards(existing,incoming) {
    if (existing.length+incoming.length>MAX_CARDS) throw Error(`카드는 ${MAX_CARDS}개 이하로 보관하세요.`);
    const ids=new Set(existing.map(c=>c.id));
    if (incoming.some(c=>ids.has(c.id))) throw Error('기존 카드와 ID가 중복됩니다. 기존 카드를 수정하거나 다른 ID를 사용하세요.');
    if(new TextEncoder().encode(pretty({schema:SCHEMA,version:1,cards:existing.concat(incoming)})).length>MAX_BYTES) {
      throw Error('전체 카드 JSON이 20 MB를 넘습니다. 발췌 범위를 줄이세요.');
    }
    return existing.concat(incoming);
  }
  if (typeof module!=='undefined'&&module.exports) {
    module.exports={fieldState,doclingObservations,markdownSignals,analyzeEvidence,validateBundle,mergeCards};return;
  }
  const el=(tag,text,cls)=>{
    const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;
  };
  const button=(text,action)=>{const n=el('button',text);n.type='button';n.addEventListener('click',action);return n;};
  const label=(text,input)=>{const n=el('label',text);n.append(input);return n;};
  const controllers=[...document.querySelectorAll('.sample-cards')].map(root=>({
    root,data:JSON.parse(root.querySelector('.sample-card-data').value),inputs:{},editing:null}));
  const documents=controllers.map(c=>c.data);
  let dirty=false;
  const bundle=()=>({schema:SCHEMA,version:1,cards:controllers.flatMap(c=>c.data.cards)});
  function download(text,name,type) {
    const url=URL.createObjectURL(new Blob([text],{type}));
    const link=el('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),10000);
  }
  for (const ctrl of controllers) {
    const {root,data,inputs}=ctrl,q=s=>root.querySelector(s),tell=t=>{q('.card-message').textContent=t;};
    ctrl.tell=tell;
    for (const tool of ['docling','tika']) {
      const panel=el('div');panel.append(el('h4',tool.toUpperCase()));
      const format=el('select');
      for (const [value,text] of [['json','원본 JSON'],['markdown','Markdown 원문'],['text','일반 텍스트 / HTML 원문']]) {
        const option=el('option',text);option.value=value;format.append(option);
      }
      format.value=tool==='docling'?'json':'markdown';
      const run=el('select');const unknown=el('option','미기록');unknown.value='';run.append(unknown);
      for (const r of data.runs[tool]) {const o=el('option',`${r.number}회 · ${r.status}`);o.value=r.number;run.append(o);}
      const content=el('textarea',undefined,'evidence-input');content.spellcheck=false;
      content.placeholder=tool==='docling'?'항목 객체·배열 또는 {"items": [...]}를 붙여넣으세요.':'같은 구간의 Markdown 또는 리소스 JSON을 붙여넣으세요.';
      const source=el('input');source.type='text';source.placeholder='예: document-001/docling-1/raw.json.gz';
      const refs=el('input');refs.type='text';refs.placeholder='예: #/texts/10, #/groups/2';
      const absent=el('input');absent.type='checkbox';
      absent.addEventListener('change',()=>{content.disabled=absent.checked;});
      panel.append(label(`${tool.toUpperCase()} 입력 형식`,format),label(`${tool.toUpperCase()} 회차`,run),
        label(`${tool.toUpperCase()} 원본 발췌`,content),label(`${tool.toUpperCase()} 원본 파일`,source),
        label(`${tool.toUpperCase()} 참조 위치 (쉼표로 구분)`,refs),label('이 도구의 증거 미입력',absent));
      q('.evidence-editors').append(panel);inputs[tool]={format,run,content,source,refs,absent};
    }
    const readEvidence=tool=>{
      const p=inputs[tool];if(p.absent.checked)return null;
      return {format:p.format.value,run:p.run.value?Number(p.run.value):null,content:p.content.value,
        source_file:p.source.value,source_refs:p.refs.value.split(',').map(s=>s.trim()).filter(Boolean)};
    };
    function reset() {
      ctrl.editing=null;
      for(const s of ['.card-title','.card-reason','.card-location','.card-note-input'])q(s).value='';
      q('.card-kind').value='headings';q('.original-checked').value='unknown';
      for(const [tool,p] of Object.entries(inputs)) {
        p.content.value='';p.source.value='';p.refs.value='';p.run.value='';
        p.format.value=tool==='docling'?'json':'markdown';p.absent.checked=false;p.content.disabled=false;
      }
      q('.create-card').textContent='비교 카드 생성';
    }
    function edit(card) {
      ctrl.editing=card.id;q('.card-title').value=card.title;q('.card-kind').value=card.kind;
      q('.card-reason').value=card.reason;q('.card-location').value=card.source_location;
      q('.card-note-input').value=card.note;q('.original-checked').value=card.original_checked==null?'unknown':String(card.original_checked);
      for(const tool of ['docling','tika']) {
        const e=card[tool],p=inputs[tool];p.absent.checked=e==null;p.content.disabled=e==null;
        p.content.value=e?.content??'';p.format.value=e?.format??(tool==='docling'?'json':'markdown');
        p.run.value=e?.run??'';p.source.value=e?.source_file??'';p.refs.value=(e?.source_refs??[]).join(', ');
      }
      q('.create-card').textContent='카드 수정 저장';q('.card-editor').open=true;q('.card-title').focus();
    }
    function render() {
      const target=q('.sample-card-list');target.replaceChildren();
      if(!data.cards.length)target.append(el('p','아직 카드가 없습니다. 같은 구간의 원본을 붙여넣거나 카드 JSON을 불러오세요.','card-empty'));
      for(const card of data.cards) {
        const article=el('article',undefined,'sample-card');
        article.append(el('h4',`${kinds[card.kind]} · ${card.title}`),el('p',card.reason||'선정 이유 미기록'));
        article.append(el('p',`원본 위치: ${card.source_location||'미기록'} · `+
          (card.original_checked===true?'작성자 기록: 원본 확인함':card.original_checked===false?'추출 결과 기반 후보':'원본 확인 여부 미기록'),'card-source'));
        article.append(el('p','문서 ID·해시 일치. 발췌 내용·참조·구간 대응은 원본과 자동 대조하지 않았습니다.','card-source'));
        const rawGrid=el('div',undefined,'grid'), observed={};
        for(const tool of ['docling','tika']) {
          const e=card[tool],col=el('div');col.append(el('h5',tool.toUpperCase()));
          if(e==null)col.append(el('p','증거 미입력 · 추출 누락 판정 아님'));
          else {
            const run=data.runs[tool].find(r=>r.number===e.run);
            col.append(el('p',`형식: ${e.format} · 회차: ${e.run??'미기록'}${run?' · '+run.status:''}\n`+
              `파일: ${e.source_file||'미기록'}\n참조: ${e.source_refs.join(', ')||'미기록'}`,'card-source'));
            const details=el('details');details.append(el('summary','원본 증거 보기'),el('pre',e.content));col.append(details);
          }
          observed[tool]=analyzeEvidence(tool,e??null);rawGrid.append(col);
        }
        article.append(rawGrid);
        const scroll=el('div',undefined,'scroll'),table=el('table'),head=el('thead'),hr=el('tr');
        ['기능','DOCLING · 제공 정보','TIKA · 제공 정보','후속 처리'].forEach(t=>hr.append(el('th',t)));
        head.append(hr);table.append(head);const body=el('tbody');
        for(const key of focus[card.kind]) {
          const row=el('tr');row.append(el('th',features[key][0]));
          for(const tool of ['docling','tika']) {
            const o=observed[tool][key],cell=el('td');
            cell.append(el('strong',o.mode),el('p',o.details,'card-observation'));row.append(cell);
          }
          row.append(el('td',`Docling: ${observed.docling[key].next}\n\nTika: ${observed.tika[key].next}`,'card-observation'));
          body.append(row);
        }
        table.append(body);scroll.append(table);article.append(scroll);
        article.append(el('p',`작성자·에이전트 메모: ${card.note||'미기록'}`,'card-note'));
        const actions=el('div',undefined,'card-actions');
        actions.append(button('카드 수정',()=>edit(card)),button('카드 삭제',()=>{
          data.cards=data.cards.filter(c=>c.id!==card.id);if(ctrl.editing===card.id)reset();dirty=true;render();
        }));article.append(actions);target.append(article);
      }
    }
    ctrl.render=render;
    q('.create-card').addEventListener('click',()=>{
      try {
        const previous=data.cards.find(c=>c.id===ctrl.editing);
        const value=q('.original-checked').value;
        const card={...previous,id:ctrl.editing||`${data.id}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
          document_id:data.id,document_sha256:data.sha256,title:q('.card-title').value,kind:q('.card-kind').value,
          reason:q('.card-reason').value,source_location:q('.card-location').value,note:q('.card-note-input').value,
          original_checked:value==='unknown'?null:value==='true',docling:readEvidence('docling'),tika:readEvidence('tika')};
        validateBundle({schema:SCHEMA,version:1,cards:[card]},documents);
        if(ctrl.editing){
          mergeCards(bundle().cards.filter(c=>c.id!==ctrl.editing),[card]);
          data.cards=data.cards.map(c=>c.id===ctrl.editing?card:c);
        }
        else {mergeCards(bundle().cards,[card]);data.cards.push(card);}
        dirty=true;reset();render();tell('카드를 생성했습니다. 공유하려면 JSON 또는 카드 포함 HTML로 저장하세요.');
      }catch(e){tell(e.message);}
    });
    q('.reset-card').addEventListener('click',reset);
    q('.import-cards').addEventListener('change',async event=>{
      const file=event.target.files[0];event.target.value='';if(!file)return;
      try {
        if(file.size>MAX_BYTES)throw Error('카드 JSON은 20 MB 이하로 불러오세요.');
        const incoming=validateBundle(JSON.parse(await file.text()),documents);
        mergeCards(bundle().cards,incoming);
        for(const c of controllers) {c.data.cards.push(...incoming.filter(x=>x.document_id===c.data.id));c.render();}
        dirty=true;tell(`${incoming.length}개 카드를 해당 문서에 추가했습니다. 원본 증거는 자동 검증하지 않았습니다.`);
      }catch(e){tell(e.message);}
    });
    q('.export-cards').addEventListener('click',()=>{
      download(pretty(bundle()),'feature-cards.json','application/json');dirty=false;
      tell('전체 카드 JSON 다운로드를 요청했습니다. 보고서 폴더에 feature-cards.json으로 두면 재생성 시 포함됩니다.');
    });
    q('.export-card-html').addEventListener('click',()=>{
      const clone=document.documentElement.cloneNode(true);
      const roots=clone.querySelectorAll('.sample-cards');
      controllers.forEach((c,i)=>{
        roots[i].querySelector('.sample-card-data').textContent=JSON.stringify(c.data);
        roots[i].querySelector('.sample-card-list').replaceChildren();
        roots[i].querySelector('.evidence-editors').replaceChildren();
        roots[i].querySelector('.card-message').textContent='';
        roots[i].querySelector('.card-editor').removeAttribute('open');
      });
      // Legacy controls are created by their own script; avoid duplicating them on reopening.
      clone.querySelectorAll('.structure-tools,.paste-grid,.review-table tbody').forEach(n=>n.replaceChildren());
      clone.querySelectorAll('.copy-text').forEach(n=>{n.textContent='';});
      download('<!doctype html>\n'+clone.outerHTML,'comparison-with-cards.html','text/html');dirty=false;
      tell('카드가 포함된 HTML 다운로드를 요청했습니다. 새 샘플 카드만 저장하며 기존 구조 검토 목록은 별도 JSON으로 저장하세요.');
    });
    try {validateBundle({schema:SCHEMA,version:1,cards:data.cards},documents);render();}
    catch(e){tell('저장된 카드 확인 필요: '+e.message);}
  }
  window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
})();
