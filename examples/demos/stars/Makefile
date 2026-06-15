# Makefile for building demos in examples/demos/stars
# Compiles each .has file to build/<name>.s -> build/<name>.o -> build/<name>.exe
# Links with library object files from build/

.SUFFIXES:

PROJ_ROOT := ../../..

# Resolve compiler runner from project root.
# Prefer `venv`, then `.venv`, then fallback to system python3.
PYTHON_BIN := $(if $(wildcard $(PROJ_ROOT)/venv/bin/python),venv/bin/python,$(if $(wildcard $(PROJ_ROOT)/.venv/bin/python),.venv/bin/python,python3))
HASC := cd "$(PROJ_ROOT)" && "$(PYTHON_BIN)" -m hasc.cli
VASM := vasmm68k_mot
VLINK := vlink

LIB_DIR := ../../../lib
BUILD_DIR := ../../../build
SRC_DIR := .

HAS_SOURCES := $(wildcard $(SRC_DIR)/*.has)
DEMO_NAMES := $(basename $(notdir $(HAS_SOURCES)))
ASM_SOURCES := $(addprefix $(BUILD_DIR)/,$(addsuffix .s,$(DEMO_NAMES)))
MAIN_OBJS := $(addprefix $(BUILD_DIR)/,$(addsuffix .o,$(DEMO_NAMES)))
EXE_FILES := $(addprefix $(BUILD_DIR)/,$(addsuffix .exe,$(DEMO_NAMES)))

LIB_OBJS := $(BUILD_DIR)/graphics.o \
            $(BUILD_DIR)/helpers.o \
            $(BUILD_DIR)/keyboard.o \
            $(BUILD_DIR)/sprite.o \
            $(BUILD_DIR)/input.o \
            $(BUILD_DIR)/heap.o \
            $(BUILD_DIR)/bob.o \
			$(BUILD_DIR)/font8x8.o \
            $(BUILD_DIR)/takeover.o

VASM_FLAGS := -m68000 -Fhunk -kick1hunks -I$(LIB_DIR)
VLINK_FLAGS := -bamigahunk -Bstatic

.PHONY: all clean run compile assemble link list amiga run-vamos

all: $(EXE_FILES)

list:
	@echo "Demos in $(SRC_DIR): $(DEMO_NAMES)"

$(BUILD_DIR):
	@mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%.exe: $(BUILD_DIR)/%.o $(LIB_OBJS)
	@echo "Linking demo + libraries -> $(notdir $@)"
	@which $(VLINK) > /dev/null || (echo "Error: $(VLINK) not found in PATH"; exit 1)
	$(VLINK) $(VLINK_FLAGS) $^ -o $@

$(BUILD_DIR)/%.o: $(BUILD_DIR)/%.s | $(BUILD_DIR)
	@echo "Assembling $(notdir $<) -> $(notdir $@)"
	@which $(VASM) > /dev/null || (echo "Error: $(VASM) not found in PATH"; exit 1)
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/$*.lst -o $@ $<

$(BUILD_DIR)/graphics.o: $(LIB_DIR)/graphics.s | $(BUILD_DIR)
	@echo "Assembling graphics.s -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/graphics.lst -o $@ $<

$(BUILD_DIR)/helpers.o: $(LIB_DIR)/helpers.s | $(BUILD_DIR)
	@echo "Assembling helpers.s -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/helpers.lst -o $@ $<

$(BUILD_DIR)/keyboard.o: $(LIB_DIR)/keyboard.s | $(BUILD_DIR)
	@echo "Assembling keyboard.s -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/keyboard.lst -o $@ $<

$(BUILD_DIR)/sprite.o: $(LIB_DIR)/sprite.s | $(BUILD_DIR)
	@echo "Assembling sprite.s -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/sprite.lst -o $@ $<

$(BUILD_DIR)/takeover.o: $(LIB_DIR)/takeover.s | $(BUILD_DIR)
	@echo "Assembling takeover.s -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/takeover.lst -o $@ $<

$(BUILD_DIR)/input.o: $(LIB_DIR)/input.s | $(BUILD_DIR)
	@echo "Assembling input.s -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/input.lst -o $@ $<

$(BUILD_DIR)/heap.o: $(LIB_DIR)/heap.s | $(BUILD_DIR)
	@echo "Assembling heap.s -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/heap.lst -o $@ $<

$(BUILD_DIR)/bob.o: $(LIB_DIR)/bob.s | $(BUILD_DIR)
	@echo "Assembling bob.s -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/bob.lst -o $@ $<

$(BUILD_DIR)/font8x8.o: $(LIB_DIR)/font8x8.s | $(BUILD_DIR)
	@echo "Assembling font8x8.s -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/font8x8.lst -o $@ $<


$(BUILD_DIR)/%.s: %.has | $(BUILD_DIR)
	@echo "Compiling $< -> $(notdir $@)"
	@mkdir -p $(dir $@)
	$(HASC) examples/demos/stars/$< -o build/$*.s

compile: $(ASM_SOURCES)
assemble: $(MAIN_OBJS)
link: $(EXE_FILES)

clean:
	rm -rf $(ASM_SOURCES) $(MAIN_OBJS) $(EXE_FILES) $(addprefix $(BUILD_DIR)/,$(addsuffix .lst,$(DEMO_NAMES)))

DEMO ?= random_pixels
TARGET_EXE := $(BUILD_DIR)/$(DEMO).exe

# Build one selected Amiga executable (e.g. `make amiga DEMO=Texts`).
amiga: $(TARGET_EXE)
	@echo "Amiga executable ready: $(TARGET_EXE)"

# Run the Amiga executable via vamos when available.
run-vamos: $(TARGET_EXE)
	@if which vamos > /dev/null; then \
		echo "Running $(TARGET_EXE) with vamos"; \
		vamos $(TARGET_EXE); \
	else \
		echo "vamos not found. Built Amiga executable: $(TARGET_EXE)"; \
		echo "Run it on Amiga/emulator manually."; \
	fi

# Keep `run` as alias for Amiga-oriented execution.
run: run-vamos
