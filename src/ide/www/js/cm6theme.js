import {EditorView} from "@codemirror/view"
import {Extension} from "@codemirror/state"
import {HighlightStyle, syntaxHighlighting} from "@codemirror/language"
import {tags as t} from "@lezer/highlight"

// Palette of colors
const EggshellWhite = "#f8f8f2",
  BrightWhite = "#fff",
  PaleSilver = "#d0d0d0",
  MedGray = "#808080",
  DkGray = "#4d4d4d",
  CharcoalGray = "#373831",
  SteelGray = "#353a42",
  DeepOlive = "#272822",
  EarthyOlive = "#75715e",
  DustyTaupe = "#49483e",
  PaleLemon = "#e6db74",
  BrightLemon = "#ffe600",
  Tangerine = "#fd971f",
  PaleMoon = "#fff8b8",
  SkyBlue = "#9cdcfe",
  MedBlue = "#4fc1ff",
  BrightAqua = "#9effff",
  ElectricLavender = "#ae81ff",
  VibrantFuchsia = "#f92672",
  DustyRose = "#bc6283",
  NeonLime = "#a6e22e";

// For invalid text, we fallback to the default text color
const invalid = EggshellWhite


// Editor theme styling
export const cooldarkTheme = EditorView.theme(
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
      backgroundColor: SteelGray,
    },
    ".cm-tooltip .cm-tooltip-arrow:before": {
      borderTopColor: "transparent",
      borderBottomColor: "transparent",
    },
    ".cm-tooltip .cm-tooltip-arrow:after": {
      borderTopColor: SteelGray,
      borderBottomColor: SteelGray,
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

// Syntax highlighting styles
export const cooldarkHighlightStyle = HighlightStyle.define([
  { tag: t.keyword, color: VibrantFuchsia },
  { tag: [t.name, t.deleted, t.character, t.macroName], color: EggshellWhite },
  { tag: [t.propertyName], color: NeonLime },
  { tag: [t.function(t.variableName)], color: SkyBlue },
  { tag: [t.labelName], color: MedBlue },
  { tag: [t.number, t.color, t.constant(t.name), t.standard(t.name)], color: ElectricLavender },
  { tag: [t.definition(t.name)], color: EggshellWhite },
  { tag: [t.separator], color: PaleMoon },
  { tag: [t.typeName, t.className, t.changed, t.annotation, t.modifier, t.self, t.namespace], color: MedBlue },
  { tag: [t.url, t.escape, t.regexp, t.link, t.special(t.string)], color: PaleLemon },
  { tag: [t.operator], color: BrightAqua },
  { tag: [t.operatorKeyword], color: VibrantFuchsia },
  { tag: [t.meta, t.comment], color: EarthyOlive },
  { tag: [t.squareBracket], color: BrightLemon },
  { tag: [t.brace], color: Tangerine },
  { tag: t.strong, fontWeight: "bold" },
  { tag: t.emphasis, fontStyle: "italic" },
  { tag: t.strikethrough, textDecoration: "line-through" },
  { tag: t.link, color: EarthyOlive, textDecoration: "underline" },
  { tag: t.heading, fontWeight: "bold", color: ElectricLavender },
  { tag: [t.atom, t.bool, t.special(t.variableName)], color: ElectricLavender },
  { tag: [t.processingInstruction, t.string, t.inserted], color: PaleLemon },
  { tag: t.invalid, color: invalid }
])

export const cooldark = [cooldarkTheme, syntaxHighlighting(cooldarkHighlightStyle)]
