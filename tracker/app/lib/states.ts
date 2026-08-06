/**
 * State reference data: name↔code maps and 2020 populations.
 * Kept in sync with src/gun_violence/data.py in the analysis repo.
 */

export const STATE_ABBR: Record<string, string> = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas",
  CA: "California", CO: "Colorado", CT: "Connecticut", DE: "Delaware",
  FL: "Florida", GA: "Georgia", HI: "Hawaii", ID: "Idaho",
  IL: "Illinois", IN: "Indiana", IA: "Iowa", KS: "Kansas",
  KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland",
  MA: "Massachusetts", MI: "Michigan", MN: "Minnesota", MS: "Mississippi",
  MO: "Missouri", MT: "Montana", NE: "Nebraska", NV: "Nevada",
  NH: "New Hampshire", NJ: "New Jersey", NM: "New Mexico", NY: "New York",
  NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma",
  OR: "Oregon", PA: "Pennsylvania", RI: "Rhode Island", SC: "South Carolina",
  SD: "South Dakota", TN: "Tennessee", TX: "Texas", UT: "Utah",
  VT: "Vermont", VA: "Virginia", WA: "Washington", WV: "West Virginia",
  WI: "Wisconsin", WY: "Wyoming",
};

export const STATE_TO_CODE: Record<string, string> = Object.fromEntries(
  Object.entries(STATE_ABBR).map(([code, name]) => [name, code]),
);

export const STATE_POPULATION: Record<string, number> = {
  Alabama: 5_223_121, Alaska: 738_003, Arizona: 7_691_212, Arkansas: 3_133_502,
  California: 39_345_844, Colorado: 6_036_620, Connecticut: 3_702_543,
  Delaware: 1_069_781, Florida: 23_659_198, Georgia: 11_401_288, Hawaii: 1_430_688,
  Idaho: 2_058_594, Illinois: 12_735_249, Indiana: 7_011_912, Iowa: 3_246_320,
  Kansas: 2_989_188, Kentucky: 4_629_682, Louisiana: 4_621_500, Maine: 1_421_310,
  Maryland: 6_285_380, Massachusetts: 7_169_608, Michigan: 10_155_806,
  Minnesota: 5_863_405, Mississippi: 2_958_148, Missouri: 6_297_538,
  Montana: 1_151_831, Nebraska: 2_030_421, Nevada: 3_310_833,
  "New Hampshire": 1_422_166, "New Jersey": 9_590_076, "New Mexico": 2_124_222,
  "New York": 20_003_435, "North Carolina": 11_343_875, "North Dakota": 805_329,
  Ohio: 11_940_399, Oklahoma: 4_148_818, Oregon: 4_281_848, Pennsylvania: 13_073_016,
  "Rhode Island": 1_118_627, "South Carolina": 5_650_232, "South Dakota": 943_078,
  Tennessee: 7_378_861, Texas: 32_101_064, Utah: 3_574_825, Vermont: 642_805,
  Virginia: 8_940_572, Washington: 8_074_082, "West Virginia": 1_764_892,
  Wisconsin: 5_988_406, Wyoming: 590_784,
};
