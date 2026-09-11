const {test} = require('node:test');
const assert = require('node:assert/strict');
const {validateClip,validateReview,freeBlocks,differences,canonical} =
  require('../src/docling_poc/comparison_review.js');

function clip(tool, text, markdown=true) {
  return {schema:'docling_poc.review_clip',version:1,mode:markdown?'markdown':'text',
    source:{tool,run:1,document_id:'d1',document_sha256:'abc',fingerprint:'f1'},
    blocks:freeBlocks(text,markdown)};
}

test('heading levels differ; unknown levels never count as matching levels',()=>{
  const a=clip('docling','## 제목'), b=clip('tika','### 제목');
  assert.match(differences(a,b),/수준 다름/);
  b.blocks[0].level=null;
  assert.match(differences(a,b),/수준 정보 부족/);
  assert.doesNotMatch(differences(a,b),/속성 일치/);
});
test('plain text, fences and bold do not become inferred headings',()=>{
  assert.equal(freeBlocks('# 제목',false)[0].kind,'unknown');
  assert.equal(freeBlocks('**굵은 제목**',true)[0].kind,'unknown');
  assert.equal(freeBlocks('```\n# 제목\n```',true).filter(b=>b.kind==='heading').length,0);
  assert.equal(freeBlocks('제목\n===',true)[0].level,1);
});
test('multiple blocks are not automatically aligned or graded as missing',()=>{
  assert.match(differences(clip('docling','첫째\n\n둘째'),clip('tika','둘째')),/내부 자동 대응 없음/);
  assert.match(differences(null,clip('tika','내용')),/원본 확인 필요/);
});
test('explicit source, schema version and positive levels are validated',()=>{
  const a=clip('docling','# 제목');
  assert.equal(validateClip(a),a);
  assert.throws(()=>validateClip({...a,version:2}));
  a.blocks[0].level=-1;assert.throws(()=>validateClip(a));
});
test('review JSON roundtrip preserves expectation and rejects invalid rows atomically',()=>{
  const p={schema:'docling_poc.manual_review',version:1,document_id:'d1',document_sha256:'abc',
    reviews:[{docling:clip('docling','## 제목'),tika:clip('tika','### 제목'),
      expected:{kind:'heading',level:2,parent:'상위 제목'},note:'원본 확인'}]};
  assert.deepEqual(validateReview(JSON.parse(JSON.stringify(p))),p);
  p.reviews.push({docling:null,tika:null,expected:{kind:'',level:null,parent:''},note:''});
  assert.throws(()=>validateReview(p));
});
test('JSON property order does not change source identity',()=>{
  assert.equal(canonical({x:1,b:{z:2,a:3}}),canonical({b:{a:3,z:2},x:1}));
});
