
export const app = window.comfyAPI.app.app;
export const api = window.comfyAPI.api.api;
export const $el = window.comfyAPI.ui.$el;

const link = document.createElement("link"); link.rel = "stylesheet";
link.href = "extensions/comfyui_controlnet_aux/index.css";
document.head.appendChild(link);

function listsort(listdata,valuestr) { listdata.sort((a,b)=> valuestr.includes(b.name) - valuestr.includes(a.name)); };

function addhide(el,searchValue) { el.classList.toggle('hide', !( 
    el.dataset.name.toLowerCase().includes(searchValue.toLowerCase()) ||  
    el.dataset.tag.toLowerCase().includes(searchValue.toLowerCase()) ||  
    el.classList.contains('Preprocessor-tag-selected') ) ) };
  
function getTagList() {  return preprolist[controlnet].map((tag, index) => { 
    return $el('label.Preprocessor-tag',   
                { dataset: { tag: tag.name, name: tag.name, index: index },  
                  $: (el) => { el.firstChild.onclick = () => { 
                    document.querySelectorAll(`.Preprocessor-tag`).forEach(tr => tr.classList.remove("Preprocessor-tag-selected"));
                    el.classList.toggle("Preprocessor-tag-selected"); }; },  },   
                [ $el("input", { type: 'checkbox', name: tag.name, value: tag.name }), 
                  $el("span", { textContent: tag.name })  ] 
            ); })};

let preprolist = {}; let controlnet = 'control_v11p_sd15_canny.pth';

async function getprepro(el){ const resp = await api.fetchApi(`/Preprocessor?name=${controlnet}`);
    preprolist[controlnet] = await resp.json(); let mlist = ["","none"];
    if(controlnet.includes("canny")){ mlist=["canny", "CannyEdgePreprocessor"] }
    else if(controlnet.includes("depth")){ mlist=["depth", "DepthAnythingV2Preprocessor"] }
    else if(controlnet.includes("lineart")){ mlist=["lineart", "LineartStandardPreprocessor"] }
    else if(controlnet.includes("tile")){ mlist=["tile", "TilePreprocessor"] }
    else if(controlnet.includes("scrib")){ mlist=["scrib", "Scribble_XDoG_Preprocessor"] }
    else if(controlnet.includes("soft")){ mlist=["soft", "HEDPreprocessor"] }
    else if(controlnet.includes("pose")){ mlist=["pose", "DWPreprocessor"] }    
    else if(controlnet.includes("normal")){ mlist=["normal", "BAE-NormalMapPreprocessor"] }
    else if(controlnet.includes("seg")){ mlist=["semseg", "OneFormer-COCO-SemSegPreprocessor"] }
    else if(controlnet.includes("shuffle")){ mlist=["shuffle", "ShufflePreprocessor"] }
    else if(controlnet.includes("ioclab_sd15_recolor")){ mlist=["image", "ImageLuminanceDetector"] }
    document.querySelector('.searchpre').value = mlist[0]; listsort(preprolist[controlnet],mlist[1]);
    el.innerHTML = ''; el.append(...getTagList()); updatalist(el); };

function updatalist(els) { const searchValue = document.querySelector('.searchpre').value;  //获取搜索框文本
    const selectedTags = Array.from(els.querySelectorAll('.Preprocessor-tag-selected')).map(el => el.dataset.tag); // 当前选中的标签
    listsort(preprolist[controlnet],selectedTags); els.innerHTML = ''; els.append(...getTagList());  // 重新排序
    els.children[0].classList.add("Preprocessor-tag-selected"); els.children[0].children[0].checked = true;
    els.querySelectorAll('.Preprocessor-tag').forEach(el => { addhide(el,searchValue); }); };  // 同时处理搜索和隐藏逻辑 

app.registerExtension({
    name: 'comfy.ControlNet Preprocessors.Preprocessor Selector',
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if(nodeData.name == 'ControlNetPreprocessorSelector'){ const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function() { this.setProperty("values",[]); this.setSize([300, 350]); 
                
                const toolsElement = $el('div.tools', [         //添加清空按钮搜索框 
                    $el('button.Empty',{ textContent: 'Empty',
                        onclick:()=>{ selectorlist[0].querySelectorAll(".searchpre").forEach(el=>{ el.value = '' });
                                      selectorlist[1].querySelectorAll(".Preprocessor-tag").forEach(el => {
                                          el.classList.remove("Preprocessor-tag-selected"); 
                                          el.classList.remove("hide"); el.children[0].checked = false }) } }),
                            
                    $el('textarea.searchpre',{ placeholder:"🔎 searchpre",
                        oninput:(e)=>{ selectorlist[1].querySelectorAll(".Preprocessor-tag").forEach(el => { addhide(el,e.target.value); }) } }) 
                ]);    
                              
                let selector = this.addDOMWidget( 'select_styles', "btn", $el('div.Preprocessor', [toolsElement, $el("ul.Preprocessor-list", [])] ) ); 
                Object.defineProperty(selector, "value", { 
                    get: () => [...selectorlist[1].querySelectorAll(".Preprocessor-tag-selected")].map(el => el.dataset.tag).join(',') || 'none' });
                    
                let selectorlist = selector.element.children;

                // 监听鼠标离开事件  
                selectorlist[1].addEventListener('mouseleave', function(e) { updatalist(this); });            
                 
                //根据controlnet模型返回预处理器列表
                const styles_id = this.widgets.find(w => w.name === 'cn'); 
                Object.defineProperty( styles_id, 'value', { get:()=> controlnet, set:(value)=>{ controlnet = value; getprepro(selectorlist[1]) } });     

                //根据选中状态返回预处理器
                

                getprepro(selectorlist[1]); return onNodeCreated;
            }
        }
    }
})