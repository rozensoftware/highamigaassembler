# Makefile for building the launchers game
# Compiles launchers.has -> launchers.s -> launchers.o
# Links with library object files from build/

# Disable built-in rules
.SUFFIXES:



# Detect OS (Windows vs Unix) using built-in Make variable
ifeq ($(OS),Windows_NT)
	IS_WINDOWS := 1
else
	IS_WINDOWS := 0
endif

# Get the project root directory (three levels up from this directory - highamigaassembler/)
PROJ_ROOT := ../../..
# Use current directory for build outputs
BUILD_ROOT := .



# --- Python detection ---
ifeq ($(OS),Windows_NT)
	PYTHON := $(CURDIR)/../../../../venv/Scripts/python.exe
	PYTHONPATH := $(CURDIR)/../../../../
	SLASH := \\
	VASM := vasmm68k_mot.exe
	VLINK := vlink.exe
	WHICH := where
else
	# Prefer venv python, fallback to system python3
	ifneq (,$(wildcard $(PROJ_ROOT)venv/bin/python))
		 PYTHON := $(PROJ_ROOT)venv/bin/python
	else
		 PYTHON := python3
	endif
	PYTHONPATH := $(PROJ_ROOT)
	SLASH := /
	VASM := vasmm68k_mot
	VLINK := vlink
	WHICH := which
endif
HASC := $(PYTHON) -m hasc.cli

# Directories
LIB_DIR := $(PROJ_ROOT)/lib
BUILD_DIR := $(BUILD_ROOT)/build
SRC_DIR := .
CURRENT_DIR := $(notdir $(PWD))
PNG_DIR := .
GEN_DIR := $(BUILD_DIR)/assets

# Files
HAS_SOURCE := launchers.has
ASM_SOURCE := $(BUILD_DIR)/launchers.s
MAIN_OBJ := $(BUILD_DIR)/launchers.o
EXE_FILE := $(BUILD_DIR)/launchers.exe

# Asset sources (PNG)
SPRITE_PNGS := $(PNG_DIR)/pointer.png
BOB_PNGS := $(PNG_DIR)/bullet.png \
			$(PNG_DIR)/enemy1.png \
			$(PNG_DIR)/expl1.png \
			$(PNG_DIR)/expl2.png \
			$(PNG_DIR)/expl3.png \
			$(PNG_DIR)/expl4.png \
			$(PNG_DIR)/expl5.png \
			$(PNG_DIR)/expl6.png \
			$(PNG_DIR)/launcher.png \
			$(PNG_DIR)/rocket.png \
			$(PNG_DIR)/ship1.png

# BOB without --add-word (use bobx_ prefix)
BOB_NO_WORD_PNGS := $(PNG_DIR)/mountains.png

# Generated includes from PNGs
SPRITE_ASM := $(SPRITE_PNGS:$(PNG_DIR)/%.png=$(GEN_DIR)/sprite_%.s)
BOB_ASM := $(BOB_PNGS:$(PNG_DIR)/%.png=$(GEN_DIR)/bob_%.s)
BOB_NO_WORD_ASM := $(BOB_NO_WORD_PNGS:$(PNG_DIR)/%.png=$(GEN_DIR)/bobx_%.s)
ASSET_INCLUDES := $(SPRITE_ASM) $(BOB_ASM) $(BOB_NO_WORD_ASM)

# Assembled asset objects
SPRITE_OBJS := $(SPRITE_ASM:$(GEN_DIR)/%.s=$(GEN_DIR)/%.o)
BOB_OBJS := $(BOB_ASM:$(GEN_DIR)/%.s=$(GEN_DIR)/%.o)
BOB_NO_WORD_OBJS := $(BOB_NO_WORD_ASM:$(GEN_DIR)/%.s=$(GEN_DIR)/%.o)
ASSET_OBJS := $(SPRITE_OBJS) $(BOB_OBJS) $(BOB_NO_WORD_OBJS)

# Library object files (compiled to build directory)
LIB_OBJS := $(BUILD_DIR)/graphics.o \
            $(BUILD_DIR)/helpers.o \
            $(BUILD_DIR)/keyboard.o \
            $(BUILD_DIR)/sprite.o \
			$(BUILD_DIR)/input.o \
			$(BUILD_DIR)/heap.o \
			$(BUILD_DIR)/bob.o \
			$(BUILD_DIR)/math.o \
			$(BUILD_DIR)/font8x8.o \
            $(BUILD_DIR)/str.o \
			$(BUILD_DIR)/ptplayer.o \
			$(BUILD_DIR)/music_data.o \
			$(BUILD_DIR)/sounds_data.o \
			$(BUILD_DIR)/pic_pic.jpg-ham6.o \
            $(BUILD_DIR)/takeover.o

# Compiler flags
# -m68000: target 68000 CPU
# -Fhunk: create object file (for linking with other objects)
# -kick1hunks: use Kickstart 1.x compatible hunks
# -L: generate listing file
# -I: include path for header files (lib dir contains hardware.i and other includes)
VASM_FLAGS := -m68000 -Fhunk -kick1hunks -I$(LIB_DIR)
VLINK_FLAGS := -bamigahunk -Bstatic

# Phony targets
.PHONY: all clean run help compile assemble link assets

# Default target
all: $(BUILD_DIR) assets $(EXE_FILE)


$(BUILD_DIR):
	@mkdir -p $(BUILD_DIR) 2>/dev/null || true

$(GEN_DIR): | $(BUILD_DIR)
	@mkdir -p $(GEN_DIR) 2>/dev/null || true

# Link: combine all object files into executable

$(EXE_FILE): $(MAIN_OBJ) $(LIB_OBJS) $(ASSET_OBJS)
	@echo "Linking main + libraries -> $(notdir $(EXE_FILE))"
ifeq ($(IS_WINDOWS),1)
	@$(WHICH) $(VLINK) >nul 2>&1 || (echo Error: $(VLINK) not found in PATH & exit 1)
else
	@$(WHICH) $(VLINK) > /dev/null || (echo "Error: $(VLINK) not found in PATH"; exit 1)
endif
	$(VLINK) $(VLINK_FLAGS) $^ -o $@

# Assemble: compile main assembly to object file

$(MAIN_OBJ): $(ASM_SOURCE) | $(BUILD_DIR)
	@echo "Assembling $(notdir $<) -> $(notdir $@)"
ifeq ($(IS_WINDOWS),1)
	@$(WHICH) $(VASM) >nul 2>&1 || (echo Error: $(VASM) not found in PATH & exit 1)
else
	@$(WHICH) $(VASM) > /dev/null || (echo "Error: $(VASM) not found in PATH"; exit 1)
endif
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/launchers.lst -o $@ $<

# Assemble library modules: build/%.o from lib/%.s

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


${BUILD_DIR}/math.o: $(LIB_DIR)/math.s | $(BUILD_DIR)
	@echo "Assembling math.s -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/math.lst -o $@ $<

$(BUILD_DIR)/font8x8.o: $(LIB_DIR)/font8x8.s | $(BUILD_DIR)
	@echo "Assembling font8x8.s -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/font8x8.lst -o $@ $<

$(BUILD_DIR)/ptplayer.o: $(LIB_DIR)/ptplayer.s | $(BUILD_DIR)
	@echo "Assembling ptplayer.s -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/ptplayer.lst -o $@ $<

$(BUILD_DIR)/music_data.o: $(SRC_DIR)/music_data.s | $(BUILD_DIR)
	@echo "Assembling music_data.s -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/music_data.lst -o $@ $<

$(BUILD_DIR)/sounds_data.o: $(SRC_DIR)/sounds_data.s | $(BUILD_DIR)
	@echo "Assembling sounds_data.s -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/sounds_data.lst -o $@ $<

$(BUILD_DIR)/pic_pic.jpg-ham6.o: $(SRC_DIR)/pic_pic.jpg-ham6.s | $(BUILD_DIR)	
	@echo "Assembling pic_pic.jpg-ham6.s -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/pic_pic.jpg-ham6.lst -o $@ $<

$(BUILD_DIR)/str.o: $(LIB_DIR)/str.s | $(BUILD_DIR)
	@echo "Assembling str.s -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(BUILD_DIR)/str.lst -o $@ $<
	
# ...existing code...
# Compile: generate assembly from HAS source


ifeq ($(OS),Windows_NT)
$(ASM_SOURCE): $(HAS_SOURCE) assets | $(BUILD_DIR)
	@echo "Compiling $(HAS_SOURCE) -> $(notdir $@)"
	@mkdir -p $(dir $@) 2>nul || if not exist $(subst /,\\,$(dir $@)) mkdir $(subst /,\\,$(dir $@))
	set PYTHONPATH=$(PYTHONPATH) && $(PYTHON) -m hasc.cli $(abspath $(HAS_SOURCE)) -o $(abspath $(ASM_SOURCE))
else
$(ASM_SOURCE): $(HAS_SOURCE) assets | $(BUILD_DIR)
	@echo "Compiling $(HAS_SOURCE) -> $(notdir $@)"
	@mkdir -p $(dir $@) 2>/dev/null || true
	@if ! command -v $(PYTHON) >/dev/null 2>&1; then \
		 echo "Error: Python interpreter '$(PYTHON)' not found. Set up venv or install python3."; \
		 exit 1; \
	fi
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m hasc.cli "$(abspath $(HAS_SOURCE))" -o "$(abspath $(ASM_SOURCE))"
endif

# Assets: run importers to generate .s include files from PNGs
assets: $(ASSET_INCLUDES)

# Sprite importer rule (pointer.png -> sprite_pointer.s)

$(GEN_DIR)/sprite_%.s: $(PNG_DIR)/%.png | $(GEN_DIR)
	$(PYTHON) $(PROJ_ROOT)/tools/sprite_importer.py $< --label-prefix sprite --outdir $(GEN_DIR)

# BOB importer rule (all other PNGs -> bob_*.s)

$(GEN_DIR)/bob_%.s: $(PNG_DIR)/%.png | $(GEN_DIR)
	$(PYTHON) $(PROJ_ROOT)/tools/bob_importer.py $< 5 --label-prefix bob --add-word --outdir $(GEN_DIR)

# BOB without --add-word (bobx_*.s)

$(GEN_DIR)/bobx_%.s: $(PNG_DIR)/%.png | $(GEN_DIR)
	$(PYTHON) $(PROJ_ROOT)/tools/bob_importer.py $< 5 --label-prefix bobx --outdir $(GEN_DIR)

# Assemble generated assets

$(GEN_DIR)/%.o: $(GEN_DIR)/%.s | $(BUILD_DIR)
	@echo "Assembling asset $(notdir $<) -> $(notdir $@)"
	$(VASM) $(VASM_FLAGS) -L $(basename $@).lst -o $@ $<

# Compile only (no assembly/linking)
compile: $(ASM_SOURCE)

# Assemble only (requires compiled .s file)
assemble: $(MAIN_OBJ)

# Link only (requires assembled .o files)
link: $(EXE_FILE)


# ...existing code...


# Help target (single definition)
help:
	@echo "Available targets:"
	@echo "  all         - Build the complete executable (default)"
	@echo "  compile     - Compile HAS to assembly only"
	@echo "  assemble    - Assemble to object file (requires vasm68000_mot)"
	@echo "  link        - Link object files (requires vlink)"
	@echo "  clean       - Remove generated files"
	@echo "  run         - Build and execute (requires vlink)"
	@echo "  install-adf - Copy executable to test.adf (requires xdftool)"
	@echo "  help        - Show this message"
	@echo ""
	@echo "Tool Configuration:"
	@echo "  If vasmm68k_mot or vlink are not in PATH, edit the Makefile"
	@echo "  and set VASM and VLINK variables to full paths."

# Clean build artifacts (moved to end)
clean:
ifeq ($(OS),Windows_NT)
	-del /Q /F $(subst /,\\,$(BUILD_DIR))\*.o $(subst /,\\,$(BUILD_DIR))\*.s $(subst /,\\,$(BUILD_DIR))\*.exe $(subst /,\\,$(BUILD_DIR))\*.lst
	-del /Q /F $(subst /,\\,$(GEN_DIR))\*.o $(subst /,\\,$(GEN_DIR))\*.s $(subst /,\\,$(GEN_DIR))\*.lst
	-if exist $(subst /,\\,$(GEN_DIR))\NUL rmdir /S /Q $(subst /,\\,$(GEN_DIR))
else
	rm -rf $(BUILD_DIR)/*.o $(BUILD_DIR)/*.s $(BUILD_DIR)/*.exe $(BUILD_DIR)/*.lst
	rm -rf $(GEN_DIR)/*.o $(GEN_DIR)/*.s $(GEN_DIR)/*.lst
endif

# Run the executable

run: $(EXE_FILE)
ifeq ($(IS_WINDOWS),1)
	$(EXE_FILE)
else
	./$(EXE_FILE)
endif

# Copy to ADF disk for testing in WinUAE

install-adf: $(EXE_FILE)
ifeq ($(IS_WINDOWS),1)
	@echo Copying $(notdir $(EXE_FILE)) to ADF disk...
	@if exist ..\..\disks\test.adf (
		xdftool ..\..\disks\test.adf write $(EXE_FILE) || echo Error: xdftool not found. Install with: choco install amitools
	) else (
		echo Error: test.adf not found
	)
else
	@echo "Copying $(notdir $(EXE_FILE)) to ADF disk..."
	@if [ -f ../../disks/test.adf ]; then \
		xdftool ../../disks/test.adf write $(EXE_FILE) || echo "Error: xdftool not found. Install with: sudo apt-get install amitools"; \
	else \
		echo "Error: test.adf not found"; \
	fi
endif
