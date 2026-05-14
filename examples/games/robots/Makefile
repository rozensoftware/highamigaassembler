# Makefile for building the robots game
# Compiles robots.has -> robots.s -> robots.o and links with all lib/*.s objects

# Disable built-in rules
.SUFFIXES:

# Linux-only configuration (Windows logic removed)

# Paths
PROJ_ROOT := ../../..
BUILD_ROOT := .
LIB_DIR := $(PROJ_ROOT)/lib
BUILD_DIR := $(BUILD_ROOT)/build
SRC_DIR := .

# Python / tools (Linux)
ifneq (,$(wildcard $(PROJ_ROOT)venv/bin/python))
	PYTHON := $(PROJ_ROOT)venv/bin/python
else
	PYTHON := python3
endif
PYTHONPATH := $(PROJ_ROOT)
VASM := vasmm68k_mot
VLINK := vlink
WHICH := which
HASC := $(PYTHON) -m hasc.cli

# Sources and targets
# Main has file (must be first for linker)
MAIN_HAS := robots.has
MAIN_OBJ := $(BUILD_DIR)/robots.o

# All other has files (auto-discovered)
OTHER_HAS := $(filter-out $(MAIN_HAS), $(wildcard *.has))
OTHER_OBJS := $(OTHER_HAS:%.has=$(BUILD_DIR)/%.o)

# All has-derived objects in correct order (main first)
HAS_OBJS := $(MAIN_OBJ) $(OTHER_OBJS)

EXE_FILE := $(BUILD_DIR)/robots.exe

LIB_SRCS := $(wildcard $(LIB_DIR)/*.s)
LIB_OBJS := $(LIB_SRCS:$(LIB_DIR)/%.s=$(BUILD_DIR)/%.o)
GAME_SRCS := $(wildcard $(SRC_DIR)/*.s)
GAME_OBJS := $(GAME_SRCS:$(SRC_DIR)/%.s=$(BUILD_DIR)/%.o)

# Flags
VASM_FLAGS := -m68000 -Fhunk -kick1hunks -I$(LIB_DIR)
VLINK_FLAGS := -bamigahunk -Bstatic

.PHONY: all clean compile assemble link run help libs game-objs

all: $(BUILD_DIR) $(EXE_FILE)

$(BUILD_DIR):
	@mkdir -p $(BUILD_DIR) 2>/dev/null || true

$(EXE_FILE): $(HAS_OBJS) $(LIB_OBJS) $(GAME_OBJS)
	@echo "Linking main + libraries -> $(notdir $(EXE_FILE))"
	@$(WHICH) $(VLINK) > /dev/null || (echo "Error: $(VLINK) not found in PATH"; exit 1)
	$(VLINK) $(VLINK_FLAGS) $^ -o $@

# Generic rule: compile and assemble all .has files
$(BUILD_DIR)/%.o: %.has | $(BUILD_DIR)
	@echo "Compiling and assembling $< -> $(notdir $@)"
	@mkdir -p $(dir $@) 2>/dev/null || true
	@if ! command -v $(PYTHON) >/dev/null 2>&1; then \
		 echo "Error: Python interpreter '$(PYTHON)' not found. Set up venv or install python3."; \
		 exit 1; \
	fi
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m hasc.cli "$(abspath $<)" -o "$(abspath $(BUILD_DIR)/$*.s)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/$*.lst -o $@ $(BUILD_DIR)/$*.s

$(MAIN_OBJ): $(MAIN_HAS) | $(BUILD_DIR)

# Assemble any lib/*.s into build/*.o
$(BUILD_DIR)/%.o: $(LIB_DIR)/%.s | $(BUILD_DIR)
	@echo "Assembling $< -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/$*.lst -o $@ $<

# Assemble any local game *.s (e.g., sounds_data.s) into build/*.o
$(BUILD_DIR)/%.o: $(SRC_DIR)/%.s | $(BUILD_DIR)
	@echo "Assembling $< -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/$*.lst -o $@ $<

compile: $(ASM_SOURCE)
assemble: $(MAIN_OBJ)
link: $(EXE_FILE)
libs: $(LIB_OBJS)
game-objs: $(GAME_OBJS)

help:
	@echo "Targets: all (default), compile, assemble, link, libs, clean, run, help"

clean:
	rm -rf $(BUILD_DIR)/*.o $(BUILD_DIR)/*.s $(BUILD_DIR)/*.exe $(BUILD_DIR)/*.lst

run: $(EXE_FILE)
	./$(EXE_FILE)
