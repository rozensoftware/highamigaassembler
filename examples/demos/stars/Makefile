# Makefile for building the random pixel demo
# Compiles random_pixels.has -> random_pixels.s -> random_pixels.o
# Links with library object files from build/

.SUFFIXES:

MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
PROJ_ROOT := $(abspath $(MAKEFILE_DIR)../../..)

HASC := cd $(PROJ_ROOT) && .venv/bin/python -m hasc.cli
VASM := vasmm68k_mot
VLINK := vlink

LIB_DIR := ../../../lib
BUILD_DIR := ../../../build
SRC_DIR := .

HAS_SOURCE := random_pixels.has
ASM_SOURCE := $(BUILD_DIR)/random_pixels.s
MAIN_OBJ := $(BUILD_DIR)/random_pixels.o
EXE_FILE := $(BUILD_DIR)/random_pixels.exe

LIB_OBJS := $(BUILD_DIR)/graphics.o \
            $(BUILD_DIR)/helpers.o \
            $(BUILD_DIR)/keyboard.o \
            $(BUILD_DIR)/sprite.o \
            $(BUILD_DIR)/input.o \
            $(BUILD_DIR)/heap.o \
            $(BUILD_DIR)/bob.o \
            $(BUILD_DIR)/takeover.o

VASM_FLAGS := -m68000 -Fhunk -kick1hunks -I$(LIB_DIR)
VLINK_FLAGS := -bamigahunk -Bstatic

.PHONY: all clean run compile assemble link

all: $(EXE_FILE)

$(BUILD_DIR):
	@mkdir -p $(BUILD_DIR)

$(EXE_FILE): $(MAIN_OBJ) $(LIB_OBJS)
	@echo "Linking demo + libraries -> $(notdir $(EXE_FILE))"
	@which $(VLINK) > /dev/null || (echo "Error: $(VLINK) not found in PATH"; exit 1)
	$(VLINK) $(VLINK_FLAGS) $^ -o $@

$(MAIN_OBJ): $(ASM_SOURCE) | $(BUILD_DIR)
	@echo "Assembling $(notdir $<) -> $(notdir $@)"
	@which $(VASM) > /dev/null || (echo "Error: $(VASM) not found in PATH"; exit 1)
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/random_pixels.lst -o $@ $<

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

$(ASM_SOURCE): $(HAS_SOURCE) | $(BUILD_DIR)
	@echo "Compiling $(HAS_SOURCE) -> $(notdir $@)"
	@mkdir -p $(dir $@)
	$(HASC) examples/demos/stars/$< -o build/random_pixels.s

compile: $(ASM_SOURCE)
assemble: $(MAIN_OBJ)
link: $(EXE_FILE)

clean:
	rm -rf $(BUILD_DIR)/random_pixels.o $(BUILD_DIR)/random_pixels.s $(BUILD_DIR)/random_pixels.exe $(BUILD_DIR)/random_pixels.lst

run: $(EXE_FILE)
	./$(EXE_FILE)
