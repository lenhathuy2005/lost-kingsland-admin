/* Form controls for structured values. Serialization is internal, never an operator task. */
(function(global){
  'use strict';
  const labels={GOLD:'Vàng',GEMS:'Tiên Ngọc',ESSENCE:'Tinh hoa',SKILL_POINT:'Điểm kỹ năng',WOOD:'Gỗ',FOOD:'Lương thực',ORE:'Quặng',hp:'HP',vitality:'Sinh lực',martialPower:'Công vật lý',mysticPower:'Công phép',armor:'Giáp',ward:'Kháng phép',speed:'Tốc độ',damage:'Sát thương',ratio:'Tỷ lệ',amount:'Số lượng',quantity:'Số lượng',weight:'Trọng số',chance:'Xác suất',minimum:'Tối thiểu',maximum:'Tối đa',min_account_level:'Cấp tài khoản tối thiểu',min_exploration_floor:'Tầng tối thiểu',account_status:'Trạng thái tài khoản',skillCoefficient:'Hệ số kỹ năng',martialScaling:'Hệ số công vật lý',mysticScaling:'Hệ số công phép',channel:'Loại sát thương',code:'Mã',assets:'Tài nguyên',items:'Vật phẩm',item_code:'Vật phẩm',rewards:'Phần thưởng',enabled:'Bật',active:'Hoạt động',scaling:'Hệ số tăng trưởng'};
  const forbidden=new Set(['__proto__','constructor','prototype']);
  const clone=value=>JSON.parse(JSON.stringify(value));
  function name(key){return labels[key]||key.replaceAll('_',' ').replace(/([a-z])([A-Z])/g,'$1 $2');}
  function parseNumber(raw){if(raw.trim()==='')throw Error('Chưa nhập số');const value=Number(raw);if(!Number.isFinite(value)||(Number.isInteger(value)&&!Number.isSafeInteger(value)))throw Error('Số không hợp lệ hoặc vượt giới hạn');return value;}
  function mount(host,initial,changed,disabled=false){
    let value=clone(initial);
    function element(tag,text){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el;}
    function button(text,action){const el=element('button',text);el.type='button';el.className='btn btn-secondary btn-small';el.disabled=disabled;el.onclick=action;return el;}
    function commit(){changed(clone(value));}
    function draw(){host.replaceChildren(node(value,v=>{value=v;commit();},''));}
    function node(current,set,key){
      const box=element('div');box.className='structured-node';
      if(current!==null&&typeof current==='object'){
        const array=Array.isArray(current);
        Object.entries(current).forEach(([childKey,child])=>{
          const row=element('div');row.className='structured-row'+(child!==null&&typeof child==='object'?' structured-group-row':'');
          row.append(element('label',array?'Mục '+(Number(childKey)+1):name(childKey)));
          row.append(node(child,next=>{current[childKey]=next;set(current);},childKey));
          row.append(button('Xóa',()=>{if(array)current.splice(Number(childKey),1);else delete current[childKey];set(current);draw();}));box.append(row);
        });
        const controls=element('div');controls.className='structured-add';
        const kind=element('select');[['number','Số'],['string','Chữ'],['boolean','Có / Không'],['object','Nhóm thông tin'],['array','Danh sách']].forEach(([v,t])=>{const o=element('option',t);o.value=v;kind.append(o);});kind.disabled=disabled;
        const keyInput=element('input');keyInput.placeholder='Tên thuộc tính';keyInput.disabled=disabled;
        const suggestions=element('select');const blank=element('option','Chọn thuộc tính / tài nguyên');blank.value='';suggestions.append(blank);
        Object.entries(labels).forEach(([v,t])=>{const o=element('option',t);o.value=v;suggestions.append(o);});suggestions.disabled=disabled;suggestions.onchange=()=>{keyInput.value=suggestions.value;};
        if(!array)controls.append(suggestions,keyInput);controls.append(kind,button(array?'Thêm mục':'Thêm thuộc tính',()=>{
          const k=array?current.length:keyInput.value.trim();
          if(!array&&(!k||forbidden.has(k)||Object.hasOwn(current,k))){keyInput.setCustomValidity('Tên trống, bị trùng hoặc không được phép');keyInput.reportValidity();return;}
          keyInput.setCustomValidity('');const next={number:0,string:'',boolean:false,object:{},array:[]}[kind.value];
          if(array&&current.length&&typeof current[0]==='object'&&current[0]!==null)current.push(clone(current[0]));else current[k]=next;
          set(current);draw();
        }));box.append(controls);return box;
      }
      const input=element(typeof current==='boolean'?'select':'input');input.disabled=disabled;
      if(typeof current==='boolean'){for(const [v,t] of [['true','Có'],['false','Không']]){const o=element('option',t);o.value=v;input.append(o);}input.value=String(current);}
      else{input.type=typeof current==='number'?'number':'text';if(input.type==='number')input.step='any';input.value=current===null?'':String(current);}
      input.oninput=()=>{try{const next=typeof current==='number'?parseNumber(input.value):typeof current==='boolean'?input.value==='true':input.value;input.setCustomValidity('');set(next);}catch(error){input.setCustomValidity(error.message);}};
      box.append(input);return box;
    }
    draw();return {value:()=>clone(value)};
  }
  function enhance(root=document){
    root.querySelectorAll('textarea:not([data-structured-ready])').forEach(area=>{
      if(area.id==='gcReward'){area.dataset.structuredReady='true';area.closest('.field')?.classList.add('hidden');return;}
      const label=area.closest('.field')?.querySelector('label');
      const candidate=['json','jsonb','ARRAY'].includes(area.dataset.kind)||/JSON/i.test(label?.textContent||'')||/^[\[{]/.test(area.value.trim());
      if(!candidate)return;
      let initial;try{initial=area.value.trim()?JSON.parse(area.value):(area.dataset.kind==='ARRAY'?[]:{});}catch{area.dataset.structuredReady='invalid';area.hidden=true;area.style.display='none';const error=document.createElement('p');error.textContent='Dữ liệu cũ không hợp lệ. Cần khôi phục dữ liệu trước khi sửa.';area.after(error);return;}
      area.dataset.structuredReady='true';area.hidden=true;area.style.display='none';
      if(label)label.textContent=label.textContent.replace(/JSON/gi,'').replace(/\(nâng cao\)/gi,'').trim();
      const host=document.createElement('div');host.className='structured-editor';area.after(host);
      mount(host,initial,value=>{area.value=JSON.stringify(value);area.dispatchEvent(new Event('change',{bubbles:true}));},area.disabled);
    });
  }
  global.StructuredEditor={mount,enhance,parseNumber};
  if(typeof document!=='undefined'){
    document.addEventListener('click',event=>{const button=event.target.closest('button');if(!button||button.closest('.structured-editor'))return;const scope=button.closest('#drawerBody,.card');if(!scope)return;const invalid=Array.from(scope.querySelectorAll('.structured-editor input,.structured-editor select')).find(el=>!el.checkValidity());if(invalid||scope.querySelector('[data-structured-ready="invalid"]')){event.preventDefault();event.stopImmediatePropagation();if(invalid)invalid.reportValidity();}},true);
    const style=document.createElement('style');style.textContent='.structured-editor{padding:10px;border:1px solid #46516a;border-radius:8px}.structured-row{display:grid;grid-template-columns:minmax(110px,1fr) minmax(160px,3fr) auto;gap:8px;align-items:start;padding:6px 0;border-bottom:1px solid #46516a44}.structured-add{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}.structured-add input,.structured-add select{max-width:200px}.structured-node input,.structured-node select{width:100%}.structured-node .structured-add input{width:auto}';document.head.append(style);
    style.textContent+='.structured-row{grid-template-columns:minmax(90px,1fr) minmax(0,2fr) auto}.structured-row>*{min-width:0}.structured-group-row{grid-template-columns:minmax(0,1fr) auto}.structured-group-row>label{grid-column:1;grid-row:1}.structured-group-row>.structured-node{grid-column:1/-1;grid-row:2;border-left:2px solid #46516a55;padding-left:10px}.structured-group-row>button{grid-column:2;grid-row:1}.structured-add>*{min-width:0;max-width:100%}.structured-node input{max-width:100%}';
    new MutationObserver(()=>enhance()).observe(document.body,{childList:true,subtree:true});enhance();
  }
})(typeof window==='undefined'?globalThis:window);
