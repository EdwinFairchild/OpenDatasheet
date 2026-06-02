#!/usr/bin/env python3
"""
chips/stm32g474.py -- the STM32G474RE chip module: curated RM0440 data layered on
top of the SVD skeleton.

Everything here is sourced from RM0440 Rev 8 register tables: provenance section
numbers, verified field ACCESS (especially status/clear registers the SVD gets
wrong), and the per-bit ENUM semantics the ST SVD omits. Edit this file to raise
fidelity. To add a *different* chip, copy this file to chips/<id>.py and replace
its data (see tools/ADDING-A-CHIP.md). build.py and svd2od.py never change.
"""
import re

# --- chip descriptor (read by build.py) ----------------------------------------
ID = "stm32g474"
SVD_FILE = "stm32g474.svd"                  # in tools/chips/
SECTIONS_FILE = "stm32g474.sections.json"   # in tools/chips/, from make_sections.py
OUT = "data/stm32g474re.json"               # relative to the project root
EMIT_ALL = True                             # emit every SVD peripheral (auto-mode)

DOC_RM = "RM0440"
RM_REV = "8"

PART = {
    "mpn": "STM32G474RE",
    "manufacturer": "STMicroelectronics",
    "family": "STM32G4",
    "revision": "rev-C",
    "lifecycle": "active",
    "packages": ["LQFP64"],
}

DOCUMENTS = [
    {"id": "RM0440", "kind": "reference-manual", "rev": "8",
     "url": "https://www.st.com/resource/en/reference_manual/rm0440-stm32g4-series-advanced-armbased-32bit-mcus-stmicroelectronics.pdf"},
    {"id": "DS12288", "kind": "datasheet", "rev": "6",
     "url": "https://www.st.com/resource/en/datasheet/stm32g474re.pdf"},
    {"id": "ARM-DDI0403", "kind": "user-guide", "rev": "E.e",
     "url": "https://developer.arm.com/documentation/ddi0403/latest"},
]


# --- reusable enum vocabularies -------------------------------------------------
EN_MODER = [
    {"value": 0, "name": "INPUT", "description": "Input mode"},
    {"value": 1, "name": "OUTPUT", "description": "General-purpose output mode"},
    {"value": 2, "name": "ALTERNATE", "description": "Alternate function mode"},
    {"value": 3, "name": "ANALOG", "description": "Analog mode (reset state)"},
]
EN_OTYPER = [
    {"value": 0, "name": "PUSH_PULL", "description": "Output push-pull (reset state)"},
    {"value": 1, "name": "OPEN_DRAIN", "description": "Output open-drain"},
]
EN_OSPEEDR = [
    {"value": 0, "name": "LOW", "description": "Low speed"},
    {"value": 1, "name": "MEDIUM", "description": "Medium speed"},
    {"value": 2, "name": "HIGH", "description": "High speed"},
    {"value": 3, "name": "VERY_HIGH", "description": "Very high speed"},
]
EN_PUPDR = [
    {"value": 0, "name": "NONE", "description": "No pull-up, no pull-down"},
    {"value": 1, "name": "PULL_UP", "description": "Pull-up"},
    {"value": 2, "name": "PULL_DOWN", "description": "Pull-down"},
    {"value": 3, "name": "RESERVED", "description": "Reserved"},
]


def _per_pin(prefix, enum, desc):
    """Build a {field: override} map applying an enum to all 16 per-pin fields."""
    return {f"{prefix}{i}": {"enum": enum, "description": f"{desc} (pin {i})"} for i in range(16)}


# --- GPIO -----------------------------------------------------------------------
_GPIO_DESC = {
    "MODER": "GPIO port mode register",
    "OTYPER": "GPIO port output type register",
    "OSPEEDR": "GPIO port output speed register",
    "PUPDR": "GPIO port pull-up/pull-down register",
    "IDR": "GPIO port input data register",
    "ODR": "GPIO port output data register",
    "BSRR": "GPIO port bit set/reset register",
    "LCKR": "GPIO port configuration lock register",
    "AFRL": "GPIO alternate function low register (pins 0-7)",
    "AFRH": "GPIO alternate function high register (pins 8-15)",
    "BRR": "GPIO port bit reset register",
}

GPIO = {
    "svd_name": "GPIOC",  # GPIOC carries the all-default reset values; A/B overridden below
    "description": "General-purpose I/O port",
    "section_keyfn": lambda bare: f"GPIOx_{bare}",
    "registers": {name: {"description": d} for name, d in _GPIO_DESC.items()},
    "fields": {
        **{"MODER": _per_pin("MODER", EN_MODER, "Port mode")},
        **{"OTYPER": {f"OT{i}": {"enum": EN_OTYPER, "description": f"Output type (pin {i})"} for i in range(16)}},
        **{"OSPEEDR": _per_pin("OSPEED", EN_OSPEEDR, "Output speed")},
        **{"PUPDR": _per_pin("PUPD", EN_PUPDR, "Pull-up/pull-down")},
    },
    "emit": [
        {"name": "GPIOA", "base_address": "0x48000000",
         "description": "General-purpose I/O port A",
         "reset_overrides": {
             "MODER": "0xABFFFFFF", "OSPEEDR": "0x0C000000", "PUPDR": "0x64000000",
         },
         "note": "PA13/PA14/PA15 reset to alternate-function (SWD: SWDIO/SWCLK/JTDI), hence MODER reset 0xABFFFFFF."},
        {"name": "GPIOB", "base_address": "0x48000400",
         "description": "General-purpose I/O port B",
         "reset_overrides": {
             "MODER": "0xFFFFFEBF", "OSPEEDR": "0x000000C0", "PUPDR": "0x00000100",
         },
         "note": "PB3/PB4 reset to alternate-function (SWD: SWO/JTRST)."},
        {"name": "GPIOC", "base_address": "0x48000800", "description": "General-purpose I/O port C"},
        {"name": "GPIOD", "base_address": "0x48000C00", "description": "General-purpose I/O port D"},
        {"name": "GPIOE", "base_address": "0x48001000", "description": "General-purpose I/O port E"},
        {"name": "GPIOF", "base_address": "0x48001400", "description": "General-purpose I/O port F"},
        {"name": "GPIOG", "base_address": "0x48001800", "description": "General-purpose I/O port G"},
    ],
}

# --- RCC ------------------------------------------------------------------------
EN_RCC_SW = [
    {"value": 0, "name": "RESERVED", "description": "Reserved"},
    {"value": 1, "name": "HSI16", "description": "HSI16 selected as system clock"},
    {"value": 2, "name": "HSE", "description": "HSE selected as system clock"},
    {"value": 3, "name": "PLL", "description": "PLL selected as system clock"},
]
EN_RCC_HPRE = [
    {"value": 0, "name": "DIV1", "description": "SYSCLK not divided (values 0-7)"},
    {"value": 8, "name": "DIV2", "description": "SYSCLK divided by 2"},
    {"value": 9, "name": "DIV4", "description": "SYSCLK divided by 4"},
    {"value": 10, "name": "DIV8", "description": "SYSCLK divided by 8"},
    {"value": 11, "name": "DIV16", "description": "SYSCLK divided by 16"},
    {"value": 12, "name": "DIV64", "description": "SYSCLK divided by 64"},
    {"value": 13, "name": "DIV128", "description": "SYSCLK divided by 128"},
    {"value": 14, "name": "DIV256", "description": "SYSCLK divided by 256"},
    {"value": 15, "name": "DIV512", "description": "SYSCLK divided by 512"},
]
EN_RCC_PPRE = [
    {"value": 0, "name": "DIV1", "description": "HCLK not divided (values 0-3)"},
    {"value": 4, "name": "DIV2", "description": "HCLK divided by 2"},
    {"value": 5, "name": "DIV4", "description": "HCLK divided by 4"},
    {"value": 6, "name": "DIV8", "description": "HCLK divided by 8"},
    {"value": 7, "name": "DIV16", "description": "HCLK divided by 16"},
]
EN_RCC_PLLSRC = [
    {"value": 0, "name": "NONE", "description": "No clock sent to PLL"},
    {"value": 1, "name": "NONE_ALT", "description": "No clock sent to PLL"},
    {"value": 2, "name": "HSI16", "description": "HSI16 clock selected as PLL clock entry"},
    {"value": 3, "name": "HSE", "description": "HSE clock selected as PLL clock entry"},
]
EN_RCC_MCOSEL = [
    {"value": 0, "name": "DISABLED", "description": "MCO output disabled"},
    {"value": 1, "name": "SYSCLK", "description": "SYSCLK system clock selected"},
    {"value": 3, "name": "HSI16", "description": "HSI16 clock selected"},
    {"value": 4, "name": "HSE", "description": "HSE clock selected"},
    {"value": 5, "name": "PLL", "description": "Main PLL clock selected"},
    {"value": 6, "name": "LSI", "description": "LSI clock selected"},
    {"value": 7, "name": "LSE", "description": "LSE clock selected"},
    {"value": 8, "name": "HSI48", "description": "Internal HSI48 clock selected"},
]


def strip_prefix(prefix):
    """Rename SVD '<PREFIX>_<REG>' -> '<REG>' for cleaner register names."""
    return lambda n: n[len(prefix) + 1:] if n.startswith(prefix + "_") else n


RCC = {
    "svd_name": "RCC",
    "description": "Reset and clock control",
    "rename": strip_prefix("RCC"),
    "section_keyfn": lambda b: f"RCC_{b}",
    "fields": {
        "CFGR": {
            "SW": {"enum": EN_RCC_SW, "description": "System clock switch"},
            "SWS": {"enum": EN_RCC_SW, "access": "read-only", "description": "System clock switch status (set by hardware)"},
            "HPRE": {"enum": EN_RCC_HPRE, "description": "AHB prescaler"},
            "PPRE1": {"enum": EN_RCC_PPRE, "description": "APB1 (low-speed) prescaler"},
            "PPRE2": {"enum": EN_RCC_PPRE, "description": "APB2 (high-speed) prescaler"},
            "MCOSEL": {"enum": EN_RCC_MCOSEL, "description": "Microcontroller clock output selection"},
        },
        "PLLCFGR": {
            "PLLSRC": {"enum": EN_RCC_PLLSRC, "description": "Main PLL entry clock source"},
        },
    },
    "emit": [{"name": "RCC"}],
}

# --- USART / UART / LPUART ------------------------------------------------------
EN_PARITY = [
    {"value": 0, "name": "EVEN", "description": "Even parity"},
    {"value": 1, "name": "ODD", "description": "Odd parity"},
]
EN_OVER8 = [
    {"value": 0, "name": "OVER16", "description": "Oversampling by 16"},
    {"value": 1, "name": "OVER8", "description": "Oversampling by 8"},
]
EN_STOP = [
    {"value": 0, "name": "STOP1", "description": "1 stop bit"},
    {"value": 1, "name": "STOP0_5", "description": "0.5 stop bit"},
    {"value": 2, "name": "STOP2", "description": "2 stop bits"},
    {"value": 3, "name": "STOP1_5", "description": "1.5 stop bits"},
]
_USART_FIELDS = {
    "CR1": {
        "PS": {"enum": EN_PARITY, "description": "Parity selection"},
        "OVER8": {"enum": EN_OVER8, "description": "Oversampling mode"},
        "M0": {"description": "Word length bit 0, with M1: 00=8 data bits, 01=9, 10=7"},
        "M1": {"description": "Word length bit 1, with M0: 00=8 data bits, 01=9, 10=7"},
    },
    "CR2": {"STOP": {"enum": EN_STOP, "description": "Number of stop bits"}},
}
# ICR is write-1-to-clear: writing 1 to a bit clears the matching USART_ISR flag.
_USART_REGS = {
    "ICR": {"access": "w1c",
            "description": "Interrupt flag clear register (write 1 to clear the matching ISR flag)"},
}

USART = {
    "svd_name": "USART1",
    "description": "Universal synchronous/asynchronous receiver transmitter",
    "section_keyfn": lambda b: f"USART_{b}",
    "fields": _USART_FIELDS,
    "registers": _USART_REGS,
    "emit": [
        {"name": "USART1", "interrupts": [{"name": "USART1", "value": 37}]},
        {"name": "USART2", "base_address": "0x40004400", "interrupts": [{"name": "USART2", "value": 38}]},
        {"name": "USART3", "base_address": "0x40004800", "interrupts": [{"name": "USART3", "value": 39}]},
    ],
}
UART = {
    "svd_name": "UART4",
    "description": "Universal asynchronous receiver transmitter",
    "section_keyfn": lambda b: f"USART_{b}",
    "fields": _USART_FIELDS,
    "registers": _USART_REGS,
    "emit": [
        {"name": "UART4", "interrupts": [{"name": "UART4", "value": 52}]},
        {"name": "UART5", "base_address": "0x40005000", "interrupts": [{"name": "UART5", "value": 53}]},
    ],
}
LPUART = {
    "svd_name": "LPUART1",
    "description": "Low-power universal asynchronous receiver transmitter",
    "section_keyfn": lambda b: f"LPUART_{b}",
    "fields": {"CR1": {"PS": {"enum": EN_PARITY, "description": "Parity selection"}},
               "CR2": {"STOP": {"enum": EN_STOP, "description": "Number of stop bits"}}},
    "registers": {"ICR": {"access": "w1c",
                          "description": "Interrupt flag clear register (write 1 to clear the matching ISR flag)"}},
    "emit": [{"name": "LPUART1", "interrupts": [{"name": "LPUART1", "value": 91}]}],
}

# --- DMA -----------------------------------------------------------------------
EN_DMA_PL = [
    {"value": 0, "name": "LOW", "description": "Low"},
    {"value": 1, "name": "MEDIUM", "description": "Medium"},
    {"value": 2, "name": "HIGH", "description": "High"},
    {"value": 3, "name": "VERY_HIGH", "description": "Very high"},
]
EN_DMA_SIZE = [
    {"value": 0, "name": "BITS8", "description": "8 bits"},
    {"value": 1, "name": "BITS16", "description": "16 bits"},
    {"value": 2, "name": "BITS32", "description": "32 bits"},
    {"value": 3, "name": "RESERVED", "description": "Reserved"},
]
EN_DMA_DIR = [
    {"value": 0, "name": "FROM_PERIPHERAL", "description": "Read from peripheral"},
    {"value": 1, "name": "FROM_MEMORY", "description": "Read from memory"},
]
_DMA_CCR_FIELDS = {
    "DIR": {"enum": EN_DMA_DIR, "description": "Data transfer direction"},
    "PSIZE": {"enum": EN_DMA_SIZE, "description": "Peripheral size"},
    "MSIZE": {"enum": EN_DMA_SIZE, "description": "Memory size"},
    "PL": {"enum": EN_DMA_PL, "description": "Channel priority level"},
}

DMA = {
    "svd_name": "DMA1",
    "description": "Direct memory access controller",
    "section_keyfn": lambda b: "DMA_" + re.sub(r"\d+$", "x", b),  # CCR1->DMA_CCRx, ISR->DMA_ISR
    "fields": {f"CCR{i}": _DMA_CCR_FIELDS for i in range(1, 9)},
    # IFCR is write-1-to-clear: writing 1 clears the matching DMA_ISR flag.
    "registers": {"IFCR": {"access": "w1c",
                           "description": "Interrupt flag clear register (write 1 to clear the matching ISR flag)"}},
    "emit": [{"name": "DMA1"}, {"name": "DMA2"}],
}

# --- DMAMUX --------------------------------------------------------------------
EN_DMAMUX_SPOL = [
    {"value": 0, "name": "NONE", "description": "No event (no synchronization, no detection)"},
    {"value": 1, "name": "RISING", "description": "Rising edge"},
    {"value": 2, "name": "FALLING", "description": "Falling edge"},
    {"value": 3, "name": "BOTH", "description": "Rising and falling edges"},
]


def _dmamux_key(b):
    if re.match(r"^C\d+CR$", b):
        return "DMAMUX_CxCR"
    if re.match(r"^RG\d+CR$", b):
        return "DMAMUX_RGxCR"
    return "DMAMUX_" + b


DMAMUX = {
    "svd_name": "DMAMUX",
    "description": "DMA request multiplexer",
    "section_keyfn": _dmamux_key,
    "fields": {
        **{f"C{i}CR": {
            "DMAREQ_ID": {"description": "DMA request line selected to route to the DMA channel "
                                        "(see RM0440 Table: DMAMUX request line mapping)"},
            "SPOL": {"enum": EN_DMAMUX_SPOL, "description": "Synchronization polarity"},
        } for i in range(16)},
    },
    "registers": {
        "CFR": {"access": "w1c", "description": "Channel clear flag register (write 1 to clear a CxCR sync overrun flag)"},
        "RGCFR": {"access": "w1c", "description": "Request generator clear flag register (write 1 to clear an overrun flag)"},
    },
    "emit": [{"name": "DMAMUX"}],
}

# --- DBGMCU --------------------------------------------------------------------
DBGMCU = {
    "svd_name": "DBGMCU",
    "description": "MCU debug support component",
    "section_keyfn": lambda b: f"DBGMCU_{b}",  # CR -> DBGMCU_CR
    "registers": {
        # SVD names diverge from the RM register titles; map explicitly.
        "IDCODE": {"section": "47.6.1", "access": "read-only", "description": "MCU device ID code register"},
        "APB1L_FZ": {"section": "47.16.4", "description": "Debug MCU APB1 freeze register 1 (DBGMCU_APB1FZR1)"},
        "APB1H_FZ": {"section": "47.16.5", "description": "Debug MCU APB1 freeze register 2 (DBGMCU_APB1FZR2)"},
        "APB2_FZ": {"section": "47.16.6", "description": "Debug MCU APB2 freeze register (DBGMCU_APB2FZR)"},
    },
    "emit": [{"name": "DBGMCU", "base_address": "0xE0042000"}],
}

# --- Timers (TIM) ---------------------------------------------------------------
EN_TIM_DIR = [
    {"value": 0, "name": "UP", "description": "Counter used as upcounter"},
    {"value": 1, "name": "DOWN", "description": "Counter used as downcounter"},
]
EN_TIM_CMS = [
    {"value": 0, "name": "EDGE", "description": "Edge-aligned mode"},
    {"value": 1, "name": "CENTER1", "description": "Center-aligned mode 1"},
    {"value": 2, "name": "CENTER2", "description": "Center-aligned mode 2"},
    {"value": 3, "name": "CENTER3", "description": "Center-aligned mode 3"},
]
EN_TIM_CKD = [
    {"value": 0, "name": "DIV1", "description": "t_DTS = t_tim_ker_ck"},
    {"value": 1, "name": "DIV2", "description": "t_DTS = 2 x t_tim_ker_ck"},
    {"value": 2, "name": "DIV4", "description": "t_DTS = 4 x t_tim_ker_ck"},
    {"value": 3, "name": "RESERVED", "description": "Reserved"},
]
_TIM_CR1_FIELDS = {
    "DIR": {"enum": EN_TIM_DIR, "description": "Counting direction (read-only in center-aligned/encoder mode)"},
    "CMS": {"enum": EN_TIM_CMS, "description": "Center-aligned mode selection"},
    "CKD": {"enum": EN_TIM_CKD, "description": "Clock division (sampling clock for filters / dead-time)"},
}
# TIMx_SR status flags are rc_w0 (read; cleared by writing 0) -> schema 'w0c'.
_TIM_SR_W0C = {"SR": {"field_access": "w0c",
                      "description": "Status register (flags are cleared by writing 0)"}}

_tim_rename = lambda n: re.sub(r"^TIM\d+_", "", n)
_TIM_ALT_DROP = {"CCMR1_Alternate", "CCMR2_Alternate"}

TIM_ADV = {  # Advanced-control timers, chapter 28
    "svd_name": "TIM1",
    "description": "Advanced-control timer",
    "rename": _tim_rename,
    "drop": _TIM_ALT_DROP,
    "section_map": {r: f"28.6.{n}" for r, n in {
        "CR1": 1, "CR2": 2, "SMCR": 3, "DIER": 4, "SR": 5, "EGR": 6, "CCMR1": 7,
        "CCMR2": 9, "CCER": 11, "CNT": 12, "PSC": 13, "ARR": 14, "RCR": 15,
        "CCR1": 16, "CCR2": 17, "CCR3": 18, "CCR4": 19, "BDTR": 20, "CCR5": 21,
        "CCR6": 22, "CCMR3": 23, "DTR2": 24, "ECR": 25, "TISEL": 26, "AF1": 27,
        "AF2": 28, "DCR": 29, "DMAR": 30}.items()},
    "fields": {"CR1": _TIM_CR1_FIELDS},
    "registers": _TIM_SR_W0C,
    "emit": [{"name": "TIM1"}, {"name": "TIM8"}, {"name": "TIM20"}],
}
TIM_GP = {  # General-purpose timers TIM2/3/4/5, chapter 29
    "svd_name": "TIM2",
    "description": "General-purpose timer (32-bit on TIM2/TIM5, 16-bit on TIM3/TIM4)",
    "rename": _tim_rename,
    "drop": _TIM_ALT_DROP,
    "section_map": {r: f"29.5.{n}" for r, n in {
        "CR1": 1, "CR2": 2, "SMCR": 3, "DIER": 4, "SR": 5, "EGR": 6, "CCMR1": 7,
        "CCMR2": 9, "CCER": 11, "CNT": 12, "PSC": 14, "ARR": 15, "CCR1": 17,
        "CCR2": 19, "CCR3": 21, "CCR4": 23, "ECR": 25, "TISEL": 26, "AF1": 27,
        "AF2": 28, "DCR": 29, "DMAR": 30}.items()},
    "fields": {"CR1": _TIM_CR1_FIELDS},
    "registers": _TIM_SR_W0C,
    "emit": [{"name": "TIM2"}, {"name": "TIM3"}, {"name": "TIM4"}, {"name": "TIM5"}],
}
TIM_GP2 = {  # General-purpose timers TIM15/16/17, chapter 30
    "svd_name": "TIM15",
    "description": "General-purpose timer (TIM15/16/17)",
    "rename": _tim_rename,
    "drop": _TIM_ALT_DROP,
    "section_map": {r: f"30.7.{n}" for r, n in {
        "CR1": 1, "CR2": 2, "SMCR": 3, "DIER": 4, "SR": 5, "EGR": 6, "CCMR1": 7,
        "CCER": 9, "CNT": 10, "PSC": 11, "ARR": 12, "RCR": 13, "CCR1": 14,
        "CCR2": 15, "BDTR": 16, "DTR2": 17, "TISEL": 18, "AF1": 19, "AF2": 20,
        "DCR": 21, "DMAR": 22}.items()},
    "fields": {"CR1": _TIM_CR1_FIELDS},
    "registers": _TIM_SR_W0C,
    # TIM16/17 share chapter 30; their identical registers are cited to the
    # representative TIM15 subsections.
    "emit": [{"name": "TIM15"}, {"name": "TIM16"}, {"name": "TIM17"}],
}
TIM_BASIC = {  # Basic timers TIM6/7, chapter 31
    "svd_name": "TIM6",
    "description": "Basic timer",
    "rename": _tim_rename,
    "section_map": {r: f"31.4.{n}" for r, n in {
        "CR1": 1, "CR2": 2, "DIER": 3, "SR": 4, "EGR": 5, "CNT": 6, "PSC": 7, "ARR": 8}.items()},
    "registers": _TIM_SR_W0C,
    "emit": [{"name": "TIM6"}, {"name": "TIM7"}],
}

# Peripherals to emit, in order. Add specs here as they are curated.
PERIPHERALS = [
    GPIO,
    RCC,
    USART,
    UART,
    LPUART,
    DMA,
    DMAMUX,
    DBGMCU,
    TIM_ADV,
    TIM_GP,
    TIM_GP2,
    TIM_BASIC,
]

# --- Auto-mode config (build.py emits every remaining SVD peripheral) -----------
# RM register-section prefix overrides where it differs from "strip trailing
# digits off the peripheral name" (the default base). Keyed by a prefix of the
# SVD peripheral name.
AUTO_PREFIX_OVERRIDE = {
    "GPIO": "GPIOx",   # RM keys are GPIOx_MODER, ...
    "SPI": "SPIx",     # RM keys are SPIx_CR1, ...
}

# Chapter-level provenance fallback for peripherals whose per-register RM
# subsections aren't in the parsed TOC (exotic naming: HRTIM; or register tables
# the TOC didn't expose: FMC/USB). A coarse-but-true citation beats a fake "TBD".
# Matched by SVD-peripheral-name prefix.
CHAPTER_FALLBACK = {
    "HRTIM": "27",          # High-resolution timer
    "FMC": "19",            # Flexible static memory controller (FSMC)
    "USB": "45",            # USB full-speed device interface
    "UCPD": "46",           # USB Type-C / Power Delivery
}

# RM0440 Rev 8-verified access for AUTO peripherals' status/clear registers. The
# SVD can't express W1C/w0c/rc, so it mis-types these (e.g. EXTI_PR1 as read-write,
# which is dangerous). Values read from the RM register-table access rows.
# Keyed by family = peripheral name with trailing digits stripped (ADC1 -> ADC).
ACCESS_FIX = {
    "ADC": {"ISR": "w1c"},            # rc_w1, cleared in place (no separate clear reg)
    "FDCAN": {"IR": "w1c"},           # rc_w1
    "EXTI": {"PR1": "w1c", "PR2": "w1c"},  # rc_w1 pending registers
    "WWDG": {"SR": "w0c"},            # EWIF is rc_w0
    "I2C": {"ISR": "read-only"},      # flags read-only (cleared via I2C_ICR)
    "PWR": {"SR1": "read-only", "SR2": "read-only"},
}
# Any auto register whose bare name is a write-1-to-clear register -> all fields w1c.
# Verified: every match is a genuine interrupt/status clear register.
CLEAR_SUFFIX = "ICR"          # I2C_ICR, LPTIM_ICR, CRS_ICR, HRTIM *ICR, ...
CLEAR_NAMES = {"SCR", "IFCR"}  # RTC_SCR, TAMP_SCR, PWR_SCR, ...

# Hand-authored peripherals not present in the SVD (ARM Cortex-M core: ITM, DWT).
# Pending a citable source (PM0214 / Armv7-M ARM) -- left empty rather than ship
# fabricated section numbers, which would violate the provenance principle.
# (Planned as dedicated ARM-core JSONs later.)
EXTRA_PERIPHERALS = []


# ============================================================================
# Tier 2 -- core electrical/limit blocks, from DS12288 Rev 6 (stm32g474cb.pdf).
# `null` (Python None) means "the datasheet does not state this value" -- shown
# to the agent as not-available rather than guessed. Conditions are mandatory on
# every electrical value (principle #5); limits follow the schema's simpler shape.
# ============================================================================
DOC_DS = "DS12288"
DS_REV = "6"


def _ds(section):
    return {"doc": DOC_DS, "section": section, "rev": DS_REV}


LIMITS = {
    "absolute_maximum": [
        {"parameter": "VDD-VSS", "description": "External main supply (incl. VDD, VDDA, VBAT, VREF+)",
         "min": -0.3, "max": 4.0, "unit": "V", "provenance": _ds("5.2 (Table 14)")},
        {"parameter": "VIN_FT_c", "description": "Input voltage on FT_c (5 V-tolerant) pins",
         "min": -0.3, "max": 5.5, "unit": "V", "provenance": _ds("5.2 (Table 14)")},
        {"parameter": "VIN", "description": "Input voltage on standard (non-5V-tolerant) pins",
         "min": -0.3, "max": 4.0, "unit": "V", "provenance": _ds("5.2 (Table 14)")},
        {"parameter": "I_VDD_total", "description": "Total current into the sum of all VDD power lines (source)",
         "min": None, "max": 150, "unit": "mA", "provenance": _ds("5.2 (Table 15)")},
        {"parameter": "T_STG", "description": "Storage temperature range",
         "min": -65, "max": 150, "unit": "degC", "provenance": _ds("5.2 (Table 16)")},
        {"parameter": "T_J", "description": "Maximum junction temperature",
         "min": None, "max": 150, "unit": "degC", "provenance": _ds("5.2 (Table 16)")},
    ],
    "recommended_operating": [
        {"parameter": "VDD", "description": "Standard operating voltage",
         "min": 1.71, "typ": None, "max": 3.6, "unit": "V", "provenance": _ds("5.3.1 (Table 17)")},
        {"parameter": "VBAT", "description": "Backup operating voltage",
         "min": 1.55, "typ": None, "max": 3.6, "unit": "V", "provenance": _ds("5.3.1 (Table 17)")},
        {"parameter": "f_HCLK", "description": "Internal AHB clock frequency",
         "min": 0, "typ": None, "max": 170, "unit": "MHz", "provenance": _ds("5.3.1 (Table 17)")},
        {"parameter": "T_A", "description": "Ambient temperature, suffix-6 (industrial) device",
         "min": -40, "typ": None, "max": 85, "unit": "degC", "provenance": _ds("5.3.1 (Table 17)")},
    ],
}

ELECTRICAL = [
    {
        "parameter": "f_HCLK_max", "symbol": "f_HCLK",
        "description": "Maximum internal AHB (HCLK) clock frequency",
        "values": [
            {"min": None, "typ": None, "max": 170, "unit": "MHz",
             "conditions": {"mode": "Voltage scaling Range 1 Boost (150 MHz < fHCLK <= 170 MHz)"}},
        ],
        "provenance": _ds("5.3.1 (Table 17)"),
    },
    {
        "parameter": "I_DD_run", "symbol": "I_DD_Run",
        "description": "Supply current in Run mode, code from flash, all peripherals enabled",
        "values": [
            {"min": None, "typ": 29.5, "max": None, "unit": "mA",
             "conditions": {"freq_hz": 170000000, "vdd_v": 3.3, "temp_c": 25,
                            "mode": "Range 1 Boost; max is temperature-dependent (see DS Table), N/A here"}},
            {"min": None, "typ": 10.5, "max": None, "unit": "mA",
             "conditions": {"freq_hz": 64000000, "vdd_v": 3.3, "temp_c": 25,
                            "mode": "Range 1; max is temperature-dependent (see DS Table), N/A here"}},
        ],
        "provenance": _ds("5.3.5 (Table - IDD Run)"),
    },
]

TIERS = [1, 2]
