# Copyright (c) 2018 The Android Open Source Project
# Copyright (c) 2018 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from copy import copy

from .common.codegen import CodeGen, VulkanAPIWrapper
from .common.vulkantypes import \
        VulkanAPI, makeVulkanTypeSimple, iterateVulkanType

from .wrapperdefs import VulkanWrapperGenerator
from .wrapperdefs import VULKAN_STREAM_VAR_NAME
from .wrapperdefs import STREAM_RET_TYPE
from .wrapperdefs import MARSHAL_INPUT_VAR_NAME
from .wrapperdefs import UNMARSHAL_INPUT_VAR_NAME
from .wrapperdefs import PARAMETERS_MARSHALING
from .wrapperdefs import API_PREFIX_MARSHAL
from .wrapperdefs import API_PREFIX_UNMARSHAL

class VulkanMarshalingCodegen(object):

    def __init__(self,
                 cgen,
                 streamVarName,
                 inputVarName,
                 marshalPrefix,
                 direction = "write",
                 forApiOutput = False,
                 dynAlloc = False):
        self.cgen = cgen
        self.direction = direction
        self.processSimple = "write" if self.direction == "write" else "read"
        self.forApiOutput = forApiOutput

        self.checked = False

        self.streamVarName = streamVarName
        self.inputVarName = inputVarName
        self.marshalPrefix = marshalPrefix

        self.exprAccessor = lambda t: self.cgen.generalAccess(t, parentVarName = self.inputVarName, asPtr = True)
        self.lenAccessor = lambda t: self.cgen.generalLengthAccess(t, parentVarName = self.inputVarName)

        self.dynAlloc = dynAlloc

    def needSkip(self, vulkanType):
        if vulkanType.isNextPointer():
            return True
        return False

    def getTypeForStreaming(self, vulkanType):
        res = copy(vulkanType)

        if not vulkanType.accessibleAsPointer():
            res = res.getForAddressAccess()

        if vulkanType.staticArrExpr:
            res = res.getForAddressAccess()

        if self.direction == "write":
            return res
        else:
            return res.getForNonConstAccess()

    def makeCastExpr(self, vulkanType):
        return "(%s)" % (
            self.cgen.makeCTypeDecl(vulkanType, useParamName=False))

    def genStreamCall(self, vulkanType, toStreamExpr, sizeExpr):
        varname = self.streamVarName
        func = self.processSimple
        cast = self.makeCastExpr(self.getTypeForStreaming(vulkanType))

        self.cgen.stmt(
            "%s->%s(%s%s, %s)" % (varname, func, cast, toStreamExpr, sizeExpr))

    def doAllocSpace(self, vulkanType):
        if self.dynAlloc and self.direction == "read":
            access = self.exprAccessor(vulkanType)
            lenAccess = self.lenAccessor(vulkanType)
            sizeof = self.cgen.sizeofExpr( \
                         vulkanType.getForValueAccess())
            if lenAccess:
                bytesExpr = "%s * %s" % (lenAccess, sizeof)
            else:
                bytesExpr = sizeof

            self.cgen.stmt( \
                "%s->alloc((void**)&%s, %s)" %
                    (self.streamVarName,
                     access, bytesExpr))

    def onCheck(self, vulkanType):

        if self.forApiOutput:
            return

        self.checked = True

        access = self.exprAccessor(vulkanType)

        needConsistencyCheck = False

        if (self.dynAlloc and self.direction == "read") or self.direction == "write":
            checkAccess = self.exprAccessor(vulkanType)
            addrExpr = "&" + checkAccess
            sizeExpr = self.cgen.sizeofExpr(vulkanType)
        else:
            checkName = "check_%s" % vulkanType.paramName
            self.cgen.stmt("%s %s" % (
                self.cgen.makeCTypeDecl(vulkanType, useParamName = False), checkName))
            checkAccess = checkName
            addrExpr = "&" + checkAccess
            sizeExpr = self.cgen.sizeofExpr(vulkanType)
            needConsistencyCheck = True

        self.genStreamCall(vulkanType.getForAddressAccess(), addrExpr, sizeExpr)

        if self.needSkip(vulkanType):
            return

        self.cgen.beginIf(access)

        if needConsistencyCheck:
            self.cgen.beginIf("!(%s)" % checkName)
            self.cgen.stmt(
                "fprintf(stderr, \"fatal: %s inconsistent between guest and host\\n\")" % (access))
            self.cgen.endIf()

    def endCheck(self, vulkanType):

        if self.needSkip(vulkanType):
            return

        if self.checked:
            self.cgen.endIf()
            self.checked = False

    def onCompoundType(self, vulkanType):

        if self.needSkip(vulkanType):
            self.cgen.line("// TODO: Unsupported : %s" %
                           self.cgen.makeCTypeDecl(vulkanType))
            return

        access = self.exprAccessor(vulkanType)
        lenAccess = self.lenAccessor(vulkanType)

        if vulkanType.pointerIndirectionLevels > 0:
            self.doAllocSpace(vulkanType)

        if lenAccess is not None:
            loopVar = "i"
            access = "%s + %s" % (access, loopVar)
            forInit = "uint32_t %s = 0" % loopVar
            forCond = "%s < (uint32_t)%s" % (loopVar, lenAccess)
            forIncr = "++%s" % loopVar
            self.cgen.beginFor(forInit, forCond, forIncr)

        accessWithCast = "%s(%s)" % (self.makeCastExpr(
            self.getTypeForStreaming(vulkanType)), access)

        self.cgen.funcCall(None, self.marshalPrefix + vulkanType.typeName,
                           [self.streamVarName, accessWithCast])

        if lenAccess is not None:
            self.cgen.endFor()

    def onString(self, vulkanType):

        access = self.exprAccessor(vulkanType)

        if self.direction == "write":
            self.cgen.stmt("%s->putString(%s)" % (self.streamVarName, access))
        else:
            castExpr = \
                self.makeCastExpr( \
                    self.getTypeForStreaming( \
                        vulkanType.getForAddressAccess()))

            self.cgen.stmt( \
                "%s->loadStringInPlace(%s&%s)" % (self.streamVarName, castExpr, access))

    def onStringArray(self, vulkanType):

        access = self.exprAccessor(vulkanType)
        lenAccess = self.lenAccessor(vulkanType)

        if self.direction == "write":
            self.cgen.stmt("saveStringArray(%s, %s, %s)" % (self.streamVarName,
                                                            access, lenAccess))
        else:
            castExpr = \
                self.makeCastExpr( \
                    self.getTypeForStreaming( \
                        vulkanType.getForAddressAccess()))

            self.cgen.stmt("%s->loadStringArrayInPlace(%s&%s)" % (self.streamVarName, castExpr, access))

    def onStaticArr(self, vulkanType):
        access = self.exprAccessor(vulkanType)
        lenAccess = self.lenAccessor(vulkanType)
        finalLenExpr = "%s * %s" % (lenAccess, self.cgen.sizeofExpr(vulkanType))
        self.genStreamCall(vulkanType, access, finalLenExpr)

    def onPointer(self, vulkanType):
        if self.needSkip(vulkanType):
            self.cgen.line("// TODO: Unsupported : %s" %
                           self.cgen.makeCTypeDecl(vulkanType))
            return

        access = self.exprAccessor(vulkanType)
        lenAccess = self.lenAccessor(vulkanType)

        self.doAllocSpace(vulkanType)

        if lenAccess is not None:
            finalLenExpr = "%s * %s" % (
                lenAccess, self.cgen.sizeofExpr(vulkanType.getForValueAccess()))
        else:
            finalLenExpr = self.cgen.sizeofExpr(vulkanType.getForValueAccess())

        self.genStreamCall(vulkanType, access, finalLenExpr)

    def onValue(self, vulkanType):
        access = self.exprAccessor(vulkanType)
        self.genStreamCall(vulkanType, access, self.cgen.sizeofExpr(vulkanType))


class VulkanMarshaling(VulkanWrapperGenerator):

    def __init__(self, module, typeInfo):
        VulkanWrapperGenerator.__init__(self, module, typeInfo)

        self.cgenHeader = CodeGen()
        self.cgenImpl = CodeGen()

        self.writeCodegen = \
            VulkanMarshalingCodegen(
                None,
                VULKAN_STREAM_VAR_NAME,
                MARSHAL_INPUT_VAR_NAME,
                API_PREFIX_MARSHAL,
                direction = "write")

        self.readCodegen = \
            VulkanMarshalingCodegen(
                None,
                VULKAN_STREAM_VAR_NAME,
                UNMARSHAL_INPUT_VAR_NAME,
                API_PREFIX_UNMARSHAL,
                direction = "read",
                dynAlloc = True)

        self.knownDefs = {}

        # Begin Vulkan API opcodes from something high
        # that is not going to interfere with renderControl
        # opcodes
        self.currentOpcode = 20000

    def onGenType(self, typeXml, name, alias):
        VulkanWrapperGenerator.onGenType(self, typeXml, name, alias)

        if name in self.knownDefs:
            return

        category = self.typeInfo.categoryOf(name)

        if category in ["struct", "union"] and not alias:

            structInfo = self.typeInfo.structs[name]

            marshalParams = PARAMETERS_MARSHALING + \
                [makeVulkanTypeSimple(True, name, 1, MARSHAL_INPUT_VAR_NAME)]
            marshalPrototype = \
                VulkanAPI(API_PREFIX_MARSHAL + name,
                          STREAM_RET_TYPE,
                          marshalParams)

            def structMarshalingDef(cgen):
                self.writeCodegen.cgen = cgen
                for member in structInfo.members:
                    iterateVulkanType(self.typeInfo, member, self.writeCodegen)

            self.module.appendHeader(
                self.cgenHeader.makeFuncDecl(marshalPrototype))
            self.module.appendImpl(
                self.cgenImpl.makeFuncImpl(
                    marshalPrototype, structMarshalingDef))

            unmarshalPrototype = \
                VulkanAPI(API_PREFIX_UNMARSHAL + name,
                          STREAM_RET_TYPE,
                          PARAMETERS_MARSHALING + [makeVulkanTypeSimple(False, name, 1, UNMARSHAL_INPUT_VAR_NAME)])

            def structUnmarshalingDef(cgen):
                self.readCodegen.cgen = cgen
                for member in structInfo.members:
                    iterateVulkanType(self.typeInfo, member, self.readCodegen)

            self.module.appendHeader(
                self.cgenHeader.makeFuncDecl(unmarshalPrototype))
            self.module.appendImpl(
                self.cgenImpl.makeFuncImpl(
                    unmarshalPrototype, structUnmarshalingDef))

    def onGenCmd(self, cmdinfo, name, alias):
        VulkanWrapperGenerator.onGenCmd(self, cmdinfo, name, alias)
        self.module.appendHeader(
            "#define OP_%s %d\n" % (name, self.currentOpcode))
        self.currentOpcode += 1
