# Makefile for building the launchers game
# Compiles launchers.has -> launchers.s -> launchers.o
# Assets via #import (emitted under build/gen and INCLUDEd into launchers.s)

.SUFFIXES:

ifeq ($(OS),Windows_NT)
	IS_WINDOWS := 1
else
	IS_WINDOWS := 0
endif

PROJ_ROOT := $(realpath ../../..)
BUILD_ROOT := .

ifeq ($(OS),Windows_NT)
	PYTHON := $(CURDIR)/../../../../.venv/Scripts/python.exe
	PYTHONPATH := $(CURDIR)/../../../../
	VASM := vasmm68k_mot.exe
	VLINK := vlink.exe
	WHICH := where
else
	ifneq (,$(wildcard $(PROJ_ROOT)/.venv/bin/python3))
		PYTHON := $(PROJ_ROOT)/.venv/bin/python3
	else ifneq (,$(wildcard $(PROJ_ROOT)/.venv/bin/python))
		PYTHON := $(PROJ_ROOT)/.venv/bin/python
	else
		PYTHON := python3
	endif
	PYTHONPATH := $(PROJ_ROOT)
	VASM := vasmm68k_mot
	VLINK := vlink
	WHICH := which
endif
HASC := $(PYTHON) -m hasc.cli
HASC_FLAGS := --asset-outdir $(BUILD_ROOT)/build/gen --force-assets

LIB_DIR := $(PROJ_ROOT)/lib
BUILD_DIR := $(BUILD_ROOT)/build
SRC_DIR := .

HAS_SOURCE := launchers.has
ASM_SOURCE := $(BUILD_DIR)/launchers.s
MAIN_OBJ := $(BUILD_DIR)/launchers.o
EXE_FILE := $(BUILD_DIR)/launchers.exe

# Libraries used by this example (audio.s pulls ptplayer.s)
LIB_OBJS := $(BUILD_DIR)/graphics.o \
            $(BUILD_DIR)/helpers.o \
            $(BUILD_DIR)/keyboard.o \
            $(BUILD_DIR)/sprite.o \
            $(BUILD_DIR)/input.o \
            $(BUILD_DIR)/heap.o \
            $(BUILD_DIR)/bob.o \
            $(BUILD_DIR)/textbob.o \
            $(BUILD_DIR)/math.o \
            $(BUILD_DIR)/font8x8.o \
            $(BUILD_DIR)/str.o \
            $(BUILD_DIR)/audio.o \
            $(BUILD_DIR)/ptplayer.o \
            $(BUILD_DIR)/copper.o \
            $(BUILD_DIR)/takeover.o

VASM_FLAGS := -m68000 -Fhunk -kick1hunks -I$(LIB_DIR)
VLINK_FLAGS := -bamigahunk -Bstatic

.PHONY: all clean run help compile assemble link

all: $(BUILD_DIR) $(EXE_FILE)

$(BUILD_DIR):
	@mkdir -p $(BUILD_DIR) 2>/dev/null || true
	@mkdir -p $(BUILD_DIR)/gen 2>/dev/null || true

$(EXE_FILE): $(MAIN_OBJ) $(LIB_OBJS)
	@echo "Linking main + libraries -> $(notdir $(EXE_FILE))"
ifeq ($(IS_WINDOWS),1)
	@$(WHICH) $(VLINK) >nul 2>&1 || (echo Error: $(VLINK) not found in PATH & exit 1)
else
	@$(WHICH) $(VLINK) > /dev/null || (echo "Error: $(VLINK) not found in PATH"; exit 1)
endif
	$(VLINK) $(VLINK_FLAGS) $^ -o $@

$(MAIN_OBJ): $(ASM_SOURCE) | $(BUILD_DIR)
	@echo "Assembling $(notdir $<) -> $(notdir $@)"
ifeq ($(IS_WINDOWS),1)
	@$(WHICH) $(VASM) >nul 2>&1 || (echo Error: $(VASM) not found in PATH & exit 1)
else
	@$(WHICH) $(VASM) > /dev/null || (echo "Error: $(VASM) not found in PATH"; exit 1)
endif
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/launchers.lst -o $@ $<

$(BUILD_DIR)/%.o: $(LIB_DIR)/%.s | $(BUILD_DIR)
	@echo "Assembling $(notdir $<) -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/$*.lst -o $@ $<

ifeq ($(OS),Windows_NT)
$(ASM_SOURCE): $(HAS_SOURCE) | $(BUILD_DIR)
	@echo "Compiling $(HAS_SOURCE) -> $(notdir $@)"
	@mkdir -p $(dir $@) 2>nul || if not exist $(subst /,\\,$(dir $@)) mkdir $(subst /,\\,$(dir $@))
	set PYTHONPATH=$(PYTHONPATH) && $(PYTHON) -m hasc.cli $(HASC_FLAGS) $(abspath $(HAS_SOURCE)) -o $(abspath $(ASM_SOURCE))
else
$(ASM_SOURCE): $(HAS_SOURCE) includes/launchers_defs.has | $(BUILD_DIR)
	@echo "Compiling $(HAS_SOURCE) -> $(notdir $@)"
	@mkdir -p $(BUILD_DIR)/gen 2>/dev/null || true
	@if ! command -v $(PYTHON) >/dev/null 2>&1; then \
		 echo "Error: Python interpreter '$(PYTHON)' not found. Set up .venv or install python3."; \
		 exit 1; \
	fi
	PYTHONPATH=$(PYTHONPATH) $(HASC) $(HASC_FLAGS) "$(abspath $(HAS_SOURCE))" -o "$(abspath $(ASM_SOURCE))"
endif

compile: $(ASM_SOURCE)
assemble: $(MAIN_OBJ)
link: $(EXE_FILE)

help:
	@echo "Available targets:"
	@echo "  all         - Build the complete executable (default)"
	@echo "  compile     - Compile HAS to assembly only"
	@echo "  assemble    - Assemble to object file"
	@echo "  link        - Link object files"
	@echo "  clean       - Remove generated files"
	@echo "  run         - Build and execute"
	@echo "  help        - Show this message"

clean:
ifeq ($(OS),Windows_NT)
	-del /Q /F $(subst /,\\,$(BUILD_DIR))\*.o $(subst /,\\,$(BUILD_DIR))\*.s $(subst /,\\,$(BUILD_DIR))\*.exe $(subst /,\\,$(BUILD_DIR))\*.lst
	-if exist $(subst /,\\,$(BUILD_DIR))\gen rmdir /S /Q $(subst /,\\,$(BUILD_DIR))\gen
else
	rm -rf $(BUILD_DIR)/*.o $(BUILD_DIR)/*.s $(BUILD_DIR)/*.exe $(BUILD_DIR)/*.lst $(BUILD_DIR)/gen
endif

run: $(EXE_FILE)
ifeq ($(IS_WINDOWS),1)
	$(EXE_FILE)
else
	./$(EXE_FILE)
endif
