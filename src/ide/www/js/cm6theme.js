import {EditorView} from "@codemirror/view"
import {Extension} from "@codemirror/state"
import {HighlightStyle, syntaxHighlighting} from "@codemirror/language"
import {tags as t} from "@lezer/highlight"

// CM5 Monokai palette and derived colors
const EggshellWhite = "#f8f8f2",
  DeepOlive = "#272822",
  EarthyOlive = "#75715e",
  DustyTaupe = "#49483e",
  PaleSilver = "#d0d0d0",
  DkGray = "#4d4d4d",
  MedGray = "#808080",
  CharcoalGray = "#373831",
  BrightWhite = "#fff",
  PaleLemon = "#e6db74",
  SoftSkyBlue = "#66d9ef",
  ElectricLavender = "#ae81ff",
  VibrantFuchsia = "#f92672",
  PistachioGreen = "#97b757",
  BurnishedBronze = "#bc9262",
  DustyRose = "#bc6283",
  OceanBlue = "#5998a6",
  NeonLime = "#a6e22e",
  BrightAqua = "#9effff",
  Tangerine = "#fd971f";

// Additional values for parts not defined in CM5
const tooltipBackground = "#353a42"

// For invalid text, we fallback to the default text color (CM5 doesn’t specify a distinct color)
const invalid = EggshellWhite


// Editor theme styling mirroring the full CM6 template
export const monokaiTheme = EditorView.theme(
  {
    "&": {
      color: EggshellWhite,
      backgroundColor: DeepOlive,
    },

    ".cm-content": {
      caretColor: EggshellWhite,
    },

    ".cm-cursor, .cm-dropCursor": { borderLeftColor: EggshellWhite },

    "&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection":
      {
        backgroundColor: DustyTaupe + " !important",
      },

    ".cm-panels": {
      backgroundColor: DeepOlive,
      color: EggshellWhite,
    },
    ".cm-panels.cm-panels-top": { borderBottom: "2px solid black" },
    ".cm-panels.cm-panels-bottom": { borderTop: "2px solid black" },

    ".cm-searchMatch": {
      backgroundColor: DustyTaupe + "59",
      outline: "1px solid " + VibrantFuchsia,
    },
    ".cm-searchMatch.cm-searchMatch-selected": {
      backgroundColor: DustyTaupe + "2f",
    },

    ".cm-activeLine": { backgroundColor: MedGray + "33" },
    ".cm-selectionMatch": { backgroundColor: DustyRose + "2a" },

    "&.cm-focused .cm-matchingBracket, &.cm-focused .cm-nonmatchingBracket": {
      textDecoration: "underline",
      color: BrightWhite,
    },

    ".cm-gutters": {
      backgroundColor: DeepOlive,
      color: DkGray,
      border: "none",
    },

    ".cm-activeLineGutter": {
      backgroundColor: CharcoalGray,
      color: PaleSilver,
    },

    ".cm-foldPlaceholder": {
      backgroundColor: "transparent",
      border: "none",
      color: PaleSilver,
    },

    ".cm-tooltip": {
      border: "none",
      backgroundColor: tooltipBackground,
    },
    ".cm-tooltip .cm-tooltip-arrow:before": {
      borderTopColor: "transparent",
      borderBottomColor: "transparent",
    },
    ".cm-tooltip .cm-tooltip-arrow:after": {
      borderTopColor: tooltipBackground,
      borderBottomColor: tooltipBackground,
    },
    ".cm-tooltip-autocomplete": {
      "& > ul > li[aria-selected]": {
        backgroundColor: CharcoalGray,
        color: EggshellWhite,
      },
    },
  },
  { dark: true }
);

// Syntax highlighting style including all CM6 template rules using CM5 colors
export const monokaiHighlightStyle = HighlightStyle.define([
  { tag: t.keyword, color: VibrantFuchsia },
  { tag: [t.name, t.deleted, t.character, t.macroName], color: EggshellWhite },
  { tag: [t.propertyName], color: NeonLime },
  { tag: [t.function(t.variableName)], color: Tangerine },
  { tag: [t.labelName], color: SoftSkyBlue },
  { tag: [t.number, t.color, t.constant(t.name), t.standard(t.name)], color: ElectricLavender },
  { tag: [t.definition(t.name), t.separator], color: EggshellWhite },
  { tag: [t.typeName, t.className, t.changed, t.annotation, t.modifier, t.self, t.namespace], color: SoftSkyBlue },
  { tag: [t.url, t.escape, t.regexp, t.link, t.special(t.string)], color: PaleLemon },
  { tag: [t.operator, t.operatorKeyword], color: EggshellWhite },
  { tag: [t.meta, t.comment], color: EarthyOlive },
  { tag: t.strong, fontWeight: "bold" },
  { tag: t.emphasis, fontStyle: "italic" },
  { tag: t.strikethrough, textDecoration: "line-through" },
  { tag: t.link, color: EarthyOlive, textDecoration: "underline" },
  { tag: t.heading, fontWeight: "bold", color: ElectricLavender },
  { tag: [t.atom, t.bool, t.special(t.variableName)], color: ElectricLavender },
  { tag: [t.processingInstruction, t.string, t.inserted], color: PaleLemon },
  { tag: t.invalid, color: invalid }
])

// Complete Monokai extension for CodeMirror 6
export const monokai = [monokaiTheme, syntaxHighlighting(monokaiHighlightStyle)]
