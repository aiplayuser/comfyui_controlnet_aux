import sys, os
from .utils import here, define_preprocessor_inputs, INPUT
from pathlib import Path
import traceback
import importlib
from .log import log, blue_text, cyan_text, get_summary, get_label
from .hint_image_enchance import NODE_CLASS_MAPPINGS as HIE_NODE_CLASS_MAPPINGS
from .hint_image_enchance import NODE_DISPLAY_NAME_MAPPINGS as HIE_NODE_DISPLAY_NAME_MAPPINGS
#Ref: https://github.com/comfyanonymous/ComfyUI/blob/76d53c4622fc06372975ed2a43ad345935b8a551/nodes.py#L17
sys.path.insert(0, str(Path(here, "src").resolve()))
for pkg_name in ["custom_controlnet_aux", "custom_mmpkg"]:
    sys.path.append(str(Path(here, "src", pkg_name).resolve()))

#Enable CPU fallback for ops not being supported by MPS like upsample_bicubic2d.out
#https://github.com/pytorch/pytorch/issues/77764
#https://github.com/Fannovel16/comfyui_controlnet_aux/issues/2#issuecomment-1763579485
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = os.getenv("PYTORCH_ENABLE_MPS_FALLBACK", '1')


def load_nodes():
    shorted_errors = []
    full_error_messages = []
    node_class_mappings = {}
    node_display_name_mappings = {}

    for filename in (here / "node_wrappers").iterdir():
        module_name = filename.stem
        if module_name.startswith('.'): continue #Skip hidden files created by the OS (e.g. [.DS_Store](https://en.wikipedia.org/wiki/.DS_Store))
        try:
            module = importlib.import_module(
                f".node_wrappers.{module_name}", package=__package__
            )
            node_class_mappings.update(getattr(module, "NODE_CLASS_MAPPINGS"))
            if hasattr(module, "NODE_DISPLAY_NAME_MAPPINGS"):
                node_display_name_mappings.update(getattr(module, "NODE_DISPLAY_NAME_MAPPINGS"))

            log.debug(f"Imported {module_name} nodes")

        except AttributeError:
            pass  # wip nodes
        except Exception:
            error_message = traceback.format_exc()
            full_error_messages.append(error_message)
            error_message = error_message.splitlines()[-1]
            shorted_errors.append(
                f"Failed to import module {module_name} because {error_message}"
            )
    
    if len(shorted_errors) > 0:
        full_err_log = '\n\n'.join(full_error_messages)
        print(f"\n\nFull error log from comfyui_controlnet_aux: \n{full_err_log}\n\n")
        log.info(
            f"Some nodes failed to load:\n\t"
            + "\n\t".join(shorted_errors)
            + "\n\n"
            + "Check that you properly installed the dependencies.\n"
            + "If you think this is a bug, please report it on the github page (https://github.com/Fannovel16/comfyui_controlnet_aux/issues)"
        )
    return node_class_mappings, node_display_name_mappings

AUX_NODE_MAPPINGS, AUX_DISPLAY_NAME_MAPPINGS = load_nodes()

#For nodes not mapping image to image or has special requirements
AIO_NOT_SUPPORTED = ["InpaintPreprocessor", "MeshGraphormer+ImpactDetector-DepthMapPreprocessor", "DiffusionEdge_Preprocessor"]
AIO_NOT_SUPPORTED += ["SavePoseKpsAsJsonFile", "FacialPartColoringFromPoseKps", "UpperBodyTrackingFromPoseKps", "RenderPeopleKps", "RenderAnimalKps"]
AIO_NOT_SUPPORTED += ["Unimatch_OptFlowPreprocessor", "MaskOptFlow"]

def preprocessor_options():
    auxs = list(AUX_NODE_MAPPINGS.keys())
    auxs.insert(0, "none")
    for name in AIO_NOT_SUPPORTED:
        if name in auxs:
            auxs.remove(name)
    return auxs


PREPROCESSOR_OPTIONS = preprocessor_options()

class AIO_Preprocessor:
    @classmethod
    def INPUT_TYPES(s):
        return define_preprocessor_inputs(
            preprocessor=INPUT.COMBO(PREPROCESSOR_OPTIONS, default="none"),
            resolution=INPUT.RESOLUTION()
        )

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "execute"

    CATEGORY = "ControlNet Preprocessors"

    def execute(self, preprocessor, image, resolution=512):
        if preprocessor == "none":
            return (image, )
        else:
            aux_class = AUX_NODE_MAPPINGS[preprocessor]
            input_types = aux_class.INPUT_TYPES()
            input_types = {
                **input_types["required"],
                **(input_types["optional"] if "optional" in input_types else {})
            }
            params = {}
            for name, input_type in input_types.items():
                if name == "image":
                    params[name] = image
                    continue

                if name == "resolution":
                    params[name] = resolution
                    continue

                if len(input_type) == 2 and ("default" in input_type[1]):
                    params[name] = input_type[1]["default"]
                    continue

                default_values = { "INT": 0, "FLOAT": 0.0 }
                if type(input_type[0]) is list:
                    for input_type_value in input_type[0]:
                        if input_type_value in default_values:
                            params[name] = default_values[input_type[0]]
                else:
                    if input_type[0] in default_values:
                        params[name] = default_values[input_type[0]]

            return getattr(aux_class(), aux_class.FUNCTION)(**params)

class ControlNetAuxSimpleAddText:
    @classmethod
    def INPUT_TYPES(s):
        return dict(
            required=dict(image=INPUT.IMAGE(), text=INPUT.STRING())
        )
    
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "execute"
    CATEGORY = "ControlNet Preprocessors"
    def execute(self, image, text):
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np
        import torch

        font = ImageFont.truetype(str((here / "NotoSans-Regular.ttf").resolve()), 40)
        img = Image.fromarray(image[0].cpu().numpy().__mul__(255.).astype(np.uint8))
        ImageDraw.Draw(img).text((0,0), text, fill=(0,255,0), font=font)
        return (torch.from_numpy(np.array(img)).unsqueeze(0) / 255.,)

class ExecuteAllControlNetPreprocessors:
    @classmethod
    def INPUT_TYPES(s):
        return define_preprocessor_inputs(resolution=INPUT.RESOLUTION())
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "execute"

    CATEGORY = "ControlNet Preprocessors"

    def execute(self, image, resolution=512):
        try:
            from comfy_execution.graph_utils import GraphBuilder
        except:
            raise RuntimeError("ExecuteAllControlNetPreprocessor requries [Execution Model Inversion](https://github.com/comfyanonymous/ComfyUI/commit/5cfe38). Update ComfyUI/SwarmUI to get this feature")
        
        graph = GraphBuilder()
        curr_outputs = []
        for preprocc in PREPROCESSOR_OPTIONS:
            preprocc_node = graph.node("AIO_Preprocessor", preprocessor=preprocc, image=image, resolution=resolution)
            hint_img = preprocc_node.out(0)
            add_text_node = graph.node("ControlNetAuxSimpleAddText", image=hint_img, text=preprocc)
            curr_outputs.append(add_text_node.out(0))
        
        while len(curr_outputs) > 1:
            _outputs = []
            for i in range(0, len(curr_outputs), 2):
                if i+1 < len(curr_outputs):
                    image_batch = graph.node("ImageBatch", image1=curr_outputs[i], image2=curr_outputs[i+1])
                    _outputs.append(image_batch.out(0))
                else:
                    _outputs.append(curr_outputs[i])
            curr_outputs = _outputs

        return {
            "result": (curr_outputs[0],),
            "expand": graph.finalize(),
        }

# class ControlNetPreprocessorSelector:
#     @classmethod
#     def INPUT_TYPES(s):
#         return {
#             "required": {
#                 "preprocessor": (PREPROCESSOR_OPTIONS,),
#             }
#         }

#     RETURN_TYPES = (PREPROCESSOR_OPTIONS,)
#     RETURN_NAMES = ("preprocessor",)
#     FUNCTION = "get_preprocessor"

#     CATEGORY = "ControlNet Preprocessors"

#     def get_preprocessor(self, preprocessor: str):
#         return (preprocessor,)

#########################################################################################################################
# 这是代码修改的部分，替换掉了上面的 ControlNetPreprocessorSelector 节点，
# 采用类似 sd-webui-controlnet 的统一加载器，把controlnet模型和预处理器放在一起管理。web文件夹内有示例工作流和演示。
from server import PromptServer
from aiohttp import web
import folder_paths, comfy.controlnet
WEB_DIRECTORY = "./web"

# import git #pip install GitPython #版本检测代码，留作备用。
# comfyui_version = len(list( git.Repo(os.path.dirname(folder_paths.__file__)).iter_commits('HEAD') ))
# WEB_DIRECTORY = "./web1" if int(comfyui_version)>3109 else "./web"
# print(f"[comfyui_controlnet_aux] | INFO -> 当前版本号为{comfyui_version}，使用{WEB_DIRECTORY}文件夹")

@PromptServer.instance.routes.get("/Preprocessor")
async def getStylesList(request): return web.json_response(PREPROCESSOR_OPTIONS)

class ControlNetPreprocessorSelector:
    @classmethod
    def INPUT_TYPES(s):
        return { "required": { "cn": ( folder_paths.get_filename_list("controlnet"), ), 
                               "image": ("IMAGE",), },
                 "hidden": { "prompt": "PROMPT", "my_unique_id": "UNIQUE_ID" }, 
                 "optional": { "resolution": ("INT", {"default": 512, "min": 64, "max": 4096, "step": 64 } ) }    }

    RETURN_TYPES = ("CONTROL_NET","IMAGE")
    FUNCTION = "get_preprocessor"
    CATEGORY = "ControlNet Preprocessors"
    OUTPUT_NODE = True

    def get_preprocessor(self, cn, image, resolution=512, prompt=None, my_unique_id=None): 
        cnmodel = comfy.controlnet.load_controlnet( folder_paths.get_full_path("controlnet", cn) )
        print(prompt)
        cnprepro = prompt[my_unique_id]["inputs"]['select_styles']
        if cnprepro == "none": return (cnmodel, image )
        else:
            aux_class = AUX_NODE_MAPPINGS[cnprepro]
            input_types = aux_class.INPUT_TYPES()
            input_types = {
                **input_types["required"],
                **(input_types["optional"] if "optional" in input_types else {})
            }
            params = {}
            for name, input_type in input_types.items():
                if name == "image":
                    params[name] = image
                    continue

                if name == "resolution":
                    params[name] = resolution
                    continue

                if len(input_type) == 2 and ("default" in input_type[1]):
                    params[name] = input_type[1]["default"]
                    continue

                default_values = { "INT": 0, "FLOAT": 0.0 }
                if input_type[0] in default_values: params[name] = default_values[input_type[0]]
                
            predict = getattr(aux_class(), aux_class.FUNCTION)(**params)

            if isinstance(predict, dict): return (cnmodel,) + predict["result"] 
            else: return (cnmodel,) + predict
##########################################################################################################################


NODE_CLASS_MAPPINGS = {
    **AUX_NODE_MAPPINGS,
    "AIO_Preprocessor": AIO_Preprocessor,
    "ControlNetPreprocessorSelector": ControlNetPreprocessorSelector,
    **HIE_NODE_CLASS_MAPPINGS,
    "ExecuteAllControlNetPreprocessors": ExecuteAllControlNetPreprocessors,
    "ControlNetAuxSimpleAddText": ControlNetAuxSimpleAddText
}

NODE_DISPLAY_NAME_MAPPINGS = {
    **AUX_DISPLAY_NAME_MAPPINGS,
    "AIO_Preprocessor": "AIO Aux Preprocessor",
    "ControlNetPreprocessorSelector": "Preprocessor Selector",
    **HIE_NODE_DISPLAY_NAME_MAPPINGS,
    "ExecuteAllControlNetPreprocessors": "Execute All ControlNet Preprocessors"
}
