// Event/state tests in an isolated DOM double; these do not replace visual browser QA.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const script=readFileSync(require.resolve('../src/docling_poc/comparison_cards.js'),'utf8');
const escape=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const unescape=s=>s.replace(/&quot;/g,'"').replace(/&gt;/g,'>').replace(/&lt;/g,'<').replace(/&amp;/g,'&');

function boot(initial) {
  const downloads=[],blobs=new Map();
  class Element {
    constructor(tag,cls='') {this.tag=tag;this.className=cls;this.children=[];this.events={};this.attrs={};this._text='';}
    append(...nodes) {for(let node of nodes){if(typeof node==='string'){const t=new Element('span');t.textContent=node;node=t;}node.parent=this;this.children.push(node);}}
    replaceChildren(...nodes) {this.children=[];this._text='';this.append(...nodes);}
    get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
    set textContent(value){this.children=[];this._text=String(value);}
    get value(){return this._value??(this.tag==='textarea'?this.textContent:'');}
    set value(value){this._value=String(value);}
    addEventListener(type,callback){(this.events[type]??=[]).push(callback);}
    async fire(type,event={}){event.target??=this;for(const cb of this.events[type]||[])await cb(event);}
    click(){if(this.tag==='a')downloads.push({name:this.download,blob:blobs.get(this.href)});return this.fire('click');}
    focus(){}
    remove(){if(this.parent)this.parent.children=this.parent.children.filter(c=>c!==this);}
    removeAttribute(key){delete this.attrs[key];}
    matches(selector){return selector.startsWith('.')?this.className.split(' ').includes(selector.slice(1)):this.tag===selector;}
    querySelectorAll(selector){
      const result=[];
      for(const part of selector.split(',')){
        const tokens=part.trim().split(/\s+/);
        const visit=node=>{for(const c of node.children){
          if(c.matches(tokens.at(-1))){let parent=c.parent,index=tokens.length-2;
            while(parent&&index>=0){if(parent.matches(tokens[index]))index--;parent=parent.parent;}
            if(index<0&&!result.includes(c))result.push(c);
          }visit(c);
        }};visit(this);
      }return result;
    }
    querySelector(selector){return this.querySelectorAll(selector)[0]??null;}
    cloneNode(deep){const n=new Element(this.tag,this.className);n.attrs={...this.attrs};n._text=this._text;
      if(deep)n.append(...this.children.map(c=>c.cloneNode(true)));return n;}
    get outerHTML(){return `<${this.tag}${this.className?' class="'+escape(this.className)+'"':''}>`+
      escape(this._text)+this.children.map(c=>c.outerHTML).join('')+`</${this.tag}>`;}
  }
  const html=new Element('html'),body=new Element('body');html.append(body);
  for(const data of initial){
    const root=new Element('div','sample-cards'),payload=new Element('textarea','sample-card-data');
    payload.textContent=JSON.stringify(data);root.append(payload);
    for(const [tag,cls] of [['div','evidence-editors'],['input','card-title'],['select','card-kind'],
      ['input','card-reason'],['input','card-location'],['textarea','card-note-input'],
      ['select','original-checked'],['details','card-editor'],['p','card-message'],
      ['div','sample-card-list'],['button','create-card'],['button','reset-card'],
      ['input','import-cards'],['button','export-cards'],['button','export-card-html']])root.append(new Element(tag,cls));
    root.querySelector('.card-kind').value='headings';root.querySelector('.original-checked').value='unknown';body.append(root);
  }
  const document={documentElement:html,body,createElement:tag=>new Element(tag),querySelectorAll:s=>html.querySelectorAll(s)};
  const context={document,window:{addEventListener(){}},Blob,TextEncoder,setTimeout(){},
    URL:{createObjectURL(blob){const id='blob:'+blobs.size;blobs.set(id,blob);return id;},revokeObjectURL(){}}};
  vm.runInNewContext(script,context);
  return {roots:document.querySelectorAll('.sample-cards'),downloads};
}
const docs=()=>[1,2].map(n=>({id:`d${n}`,name:`sample${n}`,sha256:`hash${n}`,runs:{docling:[],tika:[]},cards:[]}));
function fill(root) {
  root.querySelector('.card-title').value='목록 검증';root.querySelector('.card-kind').value='lists';
  const content=root.querySelectorAll('.evidence-input');
  content[0].value='{"label":"list_item","text":"내용","parent":{"$ref":"#/groups/0"}}';
  content[1].value='- 내용\n\n</textarea><script>UNTRUSTED</script>';
}
function buttons(root,text){return root.querySelectorAll('button').filter(b=>b.textContent===text);}

test('creating and editing a card preserves evidence and keeps documents independent',async()=>{
  const app=boot(docs()),root=app.roots[0];fill(root);
  await root.querySelector('.create-card').fire('click');
  assert.equal(root.querySelectorAll('.sample-card').length,1);
  assert.equal(app.roots[1].querySelectorAll('.sample-card').length,0);
  assert.match(root.querySelector('.sample-card').textContent,/발췌 밖 대상/);
  await buttons(root,'카드 수정')[0].fire('click');root.querySelector('.card-title').value='수정 제목';
  await root.querySelector('.create-card').fire('click');
  assert.equal(root.querySelectorAll('.sample-card').length,1);
  assert.match(root.querySelector('.sample-card').textContent,/수정 제목/);
  await root.querySelector('.export-cards').fire('click');
  const saved=JSON.parse(await app.downloads[0].blob.text());
  assert.equal(saved.cards[0].tika.content,'- 내용\n\n</textarea><script>UNTRUSTED</script>');
  await buttons(root,'카드 삭제')[0].fire('click');assert.equal(root.querySelectorAll('.sample-card').length,0);
});
test('JSON import targets the right document and rejects duplicates without partial updates',async()=>{
  const source=boot(docs());fill(source.roots[0]);await source.roots[0].querySelector('.create-card').fire('click');
  await source.roots[0].querySelector('.export-cards').fire('click');
  const payload=await source.downloads[0].blob.text();
  const app=boot(docs()),input=app.roots[1].querySelector('.import-cards');
  input.files=[{size:payload.length,text:async()=>payload}];await input.fire('change');
  assert.equal(app.roots[0].querySelectorAll('.sample-card').length,1);
  assert.equal(app.roots[1].querySelectorAll('.sample-card').length,0);
  await input.fire('change');assert.match(app.roots[1].querySelector('.card-message').textContent,/ID가 중복/);
  assert.equal(app.roots[0].querySelectorAll('.sample-card').length,1);
});
test('HTML export embeds card data safely and reinitialization does not duplicate controls',async()=>{
  const app=boot(docs()),root=app.roots[0];fill(root);await root.querySelector('.create-card').fire('click');
  await root.querySelector('.export-card-html').fire('click');
  const html=await app.downloads[0].blob.text();
  assert.ok(!html.includes('<script>UNTRUSTED</script>'));
  const contexts=[...html.matchAll(/<textarea class="sample-card-data">([\s\S]*?)<\/textarea>/g)]
    .map(match=>JSON.parse(unescape(match[1])));
  const restored=boot(contexts);
  assert.equal(restored.roots[0].querySelectorAll('.sample-card').length,1);
  assert.equal(restored.roots[0].querySelectorAll('.evidence-input').length,2);
  assert.equal(restored.roots[1].querySelectorAll('.sample-card').length,0);
});
