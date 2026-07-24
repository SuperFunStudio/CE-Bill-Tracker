// AUTO-GENERATED from tmp/design_principles.json by scripts/generate_design_teaser.py. Do not edit by hand.
// The Free teaser: per-lever headline + direction + material/product focus (front face),
// plus the grounded source bills behind the principle (back face -- each opens the bill modal).

export interface TeaserBill {
  state: string;
  billNumber: string;
  billId: number;
}

export interface TeaserExample {
  action: string;
  state: string;
  billNumber: string;
  billId: number;
  quote: string;
}

export interface FeeImpact {
  malus: boolean;
  bonus: boolean;
  setJurisdictions: string[];
  usPending: boolean;
  examples: { jurisdiction: string; amount: string }[];
}

export interface TeaserLever {
  lever: string;
  name: string;
  headline: string;
  direction: string;
  focus: string[];
  billCount: number;
  states: string[];
  evidence: { state: string; bill: string; quote: string } | null;
  examples: TeaserExample[];
  feeImpact: FeeImpact | null;
  bills: TeaserBill[];
}

export const GUIDE_COVERAGE = {"bills": 605, "states": 46, "levers": 9};

export const TEASER_LEVERS: TeaserLever[] = [
  {
    "lever": "design_for_recycling",
    "name": "Design for Recycling",
    "headline": "Design packaging to be recyclable in available systems",
    "direction": "Design packaging for reuse, recycling, or recovery if recycling impossible.",
    "focus": [
      "Packaging",
      "Electronics",
      "Batteries",
      "Organics",
      "Hazardous materials",
      "Textiles",
      "Vehicles"
    ],
    "billCount": 371,
    "states": [
      "AT",
      "AU",
      "BR",
      "CA",
      "CH",
      "CL",
      "CN",
      "CO",
      "CT",
      "CZ",
      "DC",
      "DE",
      "DK",
      "EE",
      "ES",
      "EU",
      "FI",
      "FR",
      "IE",
      "IN",
      "JP",
      "LT",
      "LU",
      "LV",
      "MD",
      "ME",
      "MN",
      "MX",
      "NJ",
      "NL",
      "NY",
      "OR",
      "PE",
      "PL",
      "RI",
      "SE",
      "SI",
      "SK",
      "UK",
      "UY",
      "VT",
      "WA"
    ],
    "evidence": {
      "state": "PL",
      "bill": "DU/2019/542",
      "quote": "Design and manufacture packaging to enable reuse and subsequent recycling, or at minimum recycling, or other recovery if recycling is not possible"
    },
    "examples": [
      {
        "action": "Design packaging for reuse, recycling, or recovery if recycling impossible.",
        "state": "PL",
        "billNumber": "DU/2019/542",
        "billId": 108371,
        "quote": "Design and manufacture packaging to enable reuse and subsequent recycling, or at minimum recycling, or other recovery if recycling is not possible"
      },
      {
        "action": "Design packaging for reuse, recycling, or recovery in sequence.",
        "state": "PL",
        "billNumber": "DU/2024/927",
        "billId": 108366,
        "quote": "Design and manufacture packaging to enable: multiple reuse and subsequent recycling; or at minimum recycling if reuse not possible; or other recovery if recycling not possible"
      },
      {
        "action": "Ensure all plastic packaging is reusable or recyclable by 2030.",
        "state": "AT",
        "billNumber": "20008902",
        "billId": 108328,
        "quote": "From 1 January 2030: only place plastic packaging on the market that is either reusable or recyclable"
      }
    ],
    "feeImpact": {
      "malus": true,
      "bonus": true,
      "setJurisdictions": [
        "BR",
        "CL",
        "CN",
        "EE",
        "ES",
        "EU",
        "FR",
        "JP",
        "NL",
        "PL",
        "SE"
      ],
      "usPending": true,
      "examples": [
        {
          "jurisdiction": "FR",
          "amount": "80.0 euros/tonne"
        }
      ]
    },
    "bills": [
      {
        "state": "PL",
        "billNumber": "DU/2019/542",
        "billId": 108371
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/927",
        "billId": 108366
      },
      {
        "state": "AT",
        "billNumber": "20008902",
        "billId": 108328
      },
      {
        "state": "BR",
        "billNumber": "2565302",
        "billId": 111365
      },
      {
        "state": "CA",
        "billNumber": "406_97_pit",
        "billId": 108587
      },
      {
        "state": "CA",
        "billNumber": "AB-2440",
        "billId": 80777
      },
      {
        "state": "CA",
        "billNumber": "SB-303",
        "billId": 733
      },
      {
        "state": "CA",
        "billNumber": "SB-343",
        "billId": 81917
      },
      {
        "state": "CA",
        "billNumber": "SB-54",
        "billId": 865
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127c954530a34",
        "billId": 108446
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127e112bb1ff4",
        "billId": 108449
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016128016d2f42e7",
        "billId": 108445
      },
      {
        "state": "CN",
        "billNumber": "ff8080816f135f46016f1d06082912c2",
        "billId": 108441
      },
      {
        "state": "CN",
        "billNumber": "ff80808175265dd40176b843949f3d0c",
        "billId": 108475
      },
      {
        "state": "CN",
        "billNumber": "ff8081817fc0f0f0017fd4fae0a7133e",
        "billId": 108450
      },
      {
        "state": "CN",
        "billNumber": "zhengce/content/2017-01/03/content_5156043.htm",
        "billId": 108496
      },
      {
        "state": "CN",
        "billNumber": "zhengce/zhengceku/2017-01/03/content_5156043.htm",
        "billId": 108497
      },
      {
        "state": "CO",
        "billNumber": "senado:ley_1672_2013",
        "billId": 111339
      },
      {
        "state": "DE",
        "billNumber": "altautov",
        "billId": 108222
      },
      {
        "state": "DE",
        "billNumber": "elektrog_2015",
        "billId": 108218
      },
      {
        "state": "DK",
        "billNumber": "lta/2014/130",
        "billId": 108401
      },
      {
        "state": "DK",
        "billNumber": "lta/2015/1453",
        "billId": 108402
      },
      {
        "state": "DK",
        "billNumber": "lta/2019/1218",
        "billId": 108404
      },
      {
        "state": "EE",
        "billNumber": "113032019103",
        "billId": 108418
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2021-5868",
        "billId": 108271
      },
      {
        "state": "EU",
        "billNumber": "31994L0062",
        "billId": 107262
      },
      {
        "state": "EU",
        "billNumber": "32000L0053",
        "billId": 107263
      },
      {
        "state": "EU",
        "billNumber": "32001D0753",
        "billId": 107453
      },
      {
        "state": "EU",
        "billNumber": "32004D0249",
        "billId": 107401
      },
      {
        "state": "EU",
        "billNumber": "32005L0064",
        "billId": 107300
      },
      {
        "state": "EU",
        "billNumber": "32006L0066",
        "billId": 107349
      },
      {
        "state": "EU",
        "billNumber": "32009L0001",
        "billId": 107386
      },
      {
        "state": "EU",
        "billNumber": "32018L0852",
        "billId": 107472
      },
      {
        "state": "EU",
        "billNumber": "32024R1781",
        "billId": 107265
      },
      {
        "state": "EU",
        "billNumber": "32025R0040",
        "billId": 107258
      },
      {
        "state": "FI",
        "billNumber": "2014/519",
        "billId": 108407
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043458675",
        "billId": 107815
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000046285336",
        "billId": 107959
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000046664100",
        "billId": 107829
      },
      {
        "state": "JP",
        "billNumber": "405M50000400034",
        "billId": 107870
      },
      {
        "state": "JP",
        "billNumber": "405M50000500001",
        "billId": 107869
      },
      {
        "state": "JP",
        "billNumber": "407M50000100061",
        "billId": 107871
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000110",
        "billId": 107855
      },
      {
        "state": "JP",
        "billNumber": "413M60000400076",
        "billId": 107885
      },
      {
        "state": "JP",
        "billNumber": "413M60000400079",
        "billId": 107881
      },
      {
        "state": "JP",
        "billNumber": "413M60000400080",
        "billId": 107903
      },
      {
        "state": "JP",
        "billNumber": "413M60000400082",
        "billId": 107899
      },
      {
        "state": "JP",
        "billNumber": "413M60000400083",
        "billId": 107897
      },
      {
        "state": "JP",
        "billNumber": "413M60000400085",
        "billId": 107900
      },
      {
        "state": "JP",
        "billNumber": "413M60000400086",
        "billId": 107902
      },
      {
        "state": "JP",
        "billNumber": "413M60000400087",
        "billId": 107896
      },
      {
        "state": "JP",
        "billNumber": "413M60000400088",
        "billId": 107901
      },
      {
        "state": "JP",
        "billNumber": "413M60000400089",
        "billId": 107898
      },
      {
        "state": "JP",
        "billNumber": "413M60000400090",
        "billId": 107890
      },
      {
        "state": "JP",
        "billNumber": "413M60000400091",
        "billId": 107888
      },
      {
        "state": "JP",
        "billNumber": "413M60000400092",
        "billId": 107889
      },
      {
        "state": "JP",
        "billNumber": "413M60000C00001",
        "billId": 107913
      },
      {
        "state": "JP",
        "billNumber": "413M60001500001",
        "billId": 107877
      },
      {
        "state": "JP",
        "billNumber": "424AC0000000057",
        "billId": 107690
      },
      {
        "state": "JP",
        "billNumber": "506AC0000000041",
        "billId": 107853
      },
      {
        "state": "JP",
        "billNumber": "508M60001400002",
        "billId": 107944
      },
      {
        "state": "JP",
        "billNumber": "508M60001440001",
        "billId": 107945
      },
      {
        "state": "LT",
        "billNumber": "TAIS.161216",
        "billId": 108429
      },
      {
        "state": "NL",
        "billNumber": "BWBR0016459",
        "billId": 108256
      },
      {
        "state": "NL",
        "billNumber": "BWBR0017053",
        "billId": 108247
      },
      {
        "state": "NL",
        "billNumber": "BWBR0018139",
        "billId": 108243
      },
      {
        "state": "NL",
        "billNumber": "BWBR0048093",
        "billId": 108233
      },
      {
        "state": "NY",
        "billNumber": "S-5027C",
        "billId": 104184
      },
      {
        "state": "PL",
        "billNumber": "DU/2015/687",
        "billId": 108396
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/150",
        "billId": 108372
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/160",
        "billId": 108369
      },
      {
        "state": "SE",
        "billNumber": "sfs-1997-185",
        "billId": 108320
      },
      {
        "state": "SE",
        "billNumber": "sfs-1997-788",
        "billId": 108319
      },
      {
        "state": "SE",
        "billNumber": "sfs-2006-1273",
        "billId": 108309
      },
      {
        "state": "SE",
        "billNumber": "sfs-2007-185",
        "billId": 108307
      },
      {
        "state": "SE",
        "billNumber": "sfs-2014-1073",
        "billId": 108299
      },
      {
        "state": "SE",
        "billNumber": "sfs-2018-1462",
        "billId": 108294
      },
      {
        "state": "SE",
        "billNumber": "sfs-2023-132",
        "billId": 108284
      },
      {
        "state": "UK",
        "billNumber": "uksi/1999/3447",
        "billId": 108137
      },
      {
        "state": "UK",
        "billNumber": "uksi/2003/2635",
        "billId": 108118
      },
      {
        "state": "UK",
        "billNumber": "uksi/2020/904",
        "billId": 108143
      },
      {
        "state": "DE",
        "billNumber": "battdg",
        "billId": 108220
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032847905",
        "billId": 107814
      },
      {
        "state": "MN",
        "billNumber": "HF-3911",
        "billId": 104216
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-3",
        "billId": 108104
      },
      {
        "state": "PL",
        "billNumber": "DU/2013/888",
        "billId": 108375
      },
      {
        "state": "PL",
        "billNumber": "DU/2020/1114",
        "billId": 108370
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1658",
        "billId": 108368
      },
      {
        "state": "LV",
        "billNumber": "57207",
        "billId": 108421
      },
      {
        "state": "CN",
        "billNumber": "2c909fdd678bf17901678bf737800631",
        "billId": 108442
      },
      {
        "state": "CN",
        "billNumber": "ff80818180e0a4410180f4acf8e12c02",
        "billId": 108472
      },
      {
        "state": "CO",
        "billNumber": "SB-25-163",
        "billId": 82272
      },
      {
        "state": "CT",
        "billNumber": "HB-5142",
        "billId": 82844
      },
      {
        "state": "EU",
        "billNumber": "32009D0292",
        "billId": 107529
      },
      {
        "state": "FI",
        "billNumber": "2021/714",
        "billId": 108406
      },
      {
        "state": "JP",
        "billNumber": "413M60000400050",
        "billId": 107895
      },
      {
        "state": "JP",
        "billNumber": "413M60000400059",
        "billId": 107892
      },
      {
        "state": "JP",
        "billNumber": "420M60000600001",
        "billId": 107931
      },
      {
        "state": "JP",
        "billNumber": "425M60001400003",
        "billId": 107933
      },
      {
        "state": "JP",
        "billNumber": "508M60001400003",
        "billId": 107943
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/2022/06/09/a266/jo/fr",
        "billId": 108413
      },
      {
        "state": "NL",
        "billNumber": "BWBR0013707",
        "billId": 108258
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/521",
        "billId": 108392
      },
      {
        "state": "PL",
        "billNumber": "DU/2020/1893",
        "billId": 108379
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/1004",
        "billId": 108387
      },
      {
        "state": "UY",
        "billNumber": "leyes/19829-2019",
        "billId": 111336
      },
      {
        "state": "CL",
        "billNumber": "1223902",
        "billId": 108278
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047483124",
        "billId": 107806
      },
      {
        "state": "NL",
        "billNumber": "BWBR0044197",
        "billId": 108234
      },
      {
        "state": "NY",
        "billNumber": "A-6193",
        "billId": 60356
      },
      {
        "state": "CH",
        "billNumber": "cc/2000/299",
        "billId": 108340
      },
      {
        "state": "CN",
        "billNumber": "ff808181927f127601936667b5d41015",
        "billId": 108465
      },
      {
        "state": "EU",
        "billNumber": "32008D0440",
        "billId": 107287
      },
      {
        "state": "EU",
        "billNumber": "32009R0641",
        "billId": 107299
      },
      {
        "state": "EU",
        "billNumber": "32023D1060",
        "billId": 107719
      },
      {
        "state": "FI",
        "billNumber": "2011/646",
        "billId": 108405
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-11",
        "billId": 108092
      },
      {
        "state": "IE",
        "billNumber": "eli/2007/si/798/made/en",
        "billId": 108326
      },
      {
        "state": "JP",
        "billNumber": "414M60001400007",
        "billId": 107923
      },
      {
        "state": "JP",
        "billNumber": "508M60000400007",
        "billId": 107946
      },
      {
        "state": "JP",
        "billNumber": "508M60000400008",
        "billId": 107948
      },
      {
        "state": "JP",
        "billNumber": "508M60000400009",
        "billId": 107947
      },
      {
        "state": "JP",
        "billNumber": "508M60000400010",
        "billId": 107951
      },
      {
        "state": "NL",
        "billNumber": "BWBR0037392",
        "billId": 108241
      },
      {
        "state": "NL",
        "billNumber": "BWBR0048299",
        "billId": 108235
      },
      {
        "state": "PL",
        "billNumber": "DU/2009/666",
        "billId": 108398
      },
      {
        "state": "PL",
        "billNumber": "DU/2015/1688",
        "billId": 108383
      },
      {
        "state": "SE",
        "billNumber": "sfs-2001-1063",
        "billId": 108312
      },
      {
        "state": "UK",
        "billNumber": "uksi/2016/1146",
        "billId": 108123
      },
      {
        "state": "CL",
        "billNumber": "1157019",
        "billId": 108277
      },
      {
        "state": "EU",
        "billNumber": "32012L0019",
        "billId": 107259
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-18",
        "billId": 108106
      },
      {
        "state": "OR",
        "billNumber": "HB-3780",
        "billId": 72412
      },
      {
        "state": "CN",
        "billNumber": "ff808081752b7d430176b1a842ea3f28",
        "billId": 108476
      },
      {
        "state": "EE",
        "billNumber": "749804",
        "billId": 108417
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2022-5809",
        "billId": 108267
      },
      {
        "state": "FI",
        "billNumber": "2014/520",
        "billId": 108408
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-17",
        "billId": 108099
      },
      {
        "state": "JP",
        "billNumber": "508M60000400011",
        "billId": 107949
      },
      {
        "state": "JP",
        "billNumber": "508M60000740002",
        "billId": 107953
      },
      {
        "state": "LV",
        "billNumber": "267716",
        "billId": 108423
      },
      {
        "state": "NL",
        "billNumber": "BWBR0034782",
        "billId": 108245
      },
      {
        "state": "PL",
        "billNumber": "DU/2005/1495",
        "billId": 108386
      },
      {
        "state": "PL",
        "billNumber": "DU/2017/2056",
        "billId": 108373
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/1895",
        "billId": 108380
      },
      {
        "state": "SI",
        "billNumber": "2021-01-1053",
        "billId": 108432
      },
      {
        "state": "MN",
        "billNumber": "SF-4679",
        "billId": 1222
      },
      {
        "state": "EU",
        "billNumber": "32025R0351",
        "billId": 107713
      },
      {
        "state": "JP",
        "billNumber": "407AC0000000112",
        "billId": 107693
      },
      {
        "state": "JP",
        "billNumber": "403AC0000000048",
        "billId": 107692
      },
      {
        "state": "BR",
        "billNumber": "2557024",
        "billId": 111358
      },
      {
        "state": "BR",
        "billNumber": "2599692",
        "billId": 111364
      },
      {
        "state": "BR",
        "billNumber": "_ato2023-2026/2023/decreto/D11413.htm",
        "billId": 108334
      },
      {
        "state": "BR",
        "billNumber": "_ato2023-2026/2025/decreto/D12688.htm",
        "billId": 108335
      },
      {
        "state": "CH",
        "billNumber": "cc/2021/633",
        "billId": 108337
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127fab8a83b90",
        "billId": 108471
      },
      {
        "state": "CN",
        "billNumber": "ff8080816f3e9784016f424f1b4a04d9",
        "billId": 108443
      },
      {
        "state": "CN",
        "billNumber": "ff808181799def980179ad26f28814aa",
        "billId": 108463
      },
      {
        "state": "CN",
        "billNumber": "ff8081818364d903018407f6c4887544",
        "billId": 108461
      },
      {
        "state": "CN",
        "billNumber": "ff8081818a1cb709018a24ff766d20df",
        "billId": 108469
      },
      {
        "state": "CN",
        "billNumber": "ff808181927f0931019325530cb6751c",
        "billId": 108464
      },
      {
        "state": "CN",
        "billNumber": "ff808181927f12760194167453206544",
        "billId": 108467
      },
      {
        "state": "CO",
        "billNumber": "HB-22-1355",
        "billId": 72416
      },
      {
        "state": "CO",
        "billNumber": "HB22-1355",
        "billId": 104215
      },
      {
        "state": "CZ",
        "billNumber": "2020/542",
        "billId": 108439
      },
      {
        "state": "DE",
        "billNumber": "krwg",
        "billId": 108221
      },
      {
        "state": "DK",
        "billNumber": "lta/2019/1337",
        "billId": 108403
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2006-9832",
        "billId": 108273
      },
      {
        "state": "EU",
        "billNumber": "31999D0042",
        "billId": 107452
      },
      {
        "state": "EU",
        "billNumber": "31999D0823",
        "billId": 107276
      },
      {
        "state": "EU",
        "billNumber": "32001D0524",
        "billId": 107336
      },
      {
        "state": "EU",
        "billNumber": "32002D0204",
        "billId": 107542
      },
      {
        "state": "EU",
        "billNumber": "32004L0012",
        "billId": 107378
      },
      {
        "state": "EU",
        "billNumber": "32012R1179",
        "billId": 107491
      },
      {
        "state": "EU",
        "billNumber": "32018L0849",
        "billId": 107511
      },
      {
        "state": "EU",
        "billNumber": "32018L0851",
        "billId": 107294
      },
      {
        "state": "EU",
        "billNumber": "32021D1752",
        "billId": 107618
      },
      {
        "state": "EU",
        "billNumber": "32022R1616",
        "billId": 107638
      },
      {
        "state": "FI",
        "billNumber": "2021/1029",
        "billId": 108409
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000025423069",
        "billId": 108042
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000029387124",
        "billId": 108010
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032187830",
        "billId": 108011
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043799891",
        "billId": 107990
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000053625694",
        "billId": 107832
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10",
        "billId": 108100
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-1",
        "billId": 108096
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-12",
        "billId": 108102
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/281/made/en",
        "billId": 108325
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/282/made/en",
        "billId": 108324
      },
      {
        "state": "IN",
        "billNumber": "183723",
        "billId": 111390
      },
      {
        "state": "IN",
        "billNumber": "227250",
        "billId": 111389
      },
      {
        "state": "JP",
        "billNumber": "345AC0000000137",
        "billId": 107854
      },
      {
        "state": "JP",
        "billNumber": "410AC0000000097",
        "billId": 107691
      },
      {
        "state": "JP",
        "billNumber": "410CO0000000378",
        "billId": 107859
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000104",
        "billId": 107697
      },
      {
        "state": "JP",
        "billNumber": "413CO0000000176",
        "billId": 107861
      },
      {
        "state": "JP",
        "billNumber": "413M60001400001",
        "billId": 107915
      },
      {
        "state": "JP",
        "billNumber": "413M60001F40004",
        "billId": 107921
      },
      {
        "state": "JP",
        "billNumber": "503AC0000000060",
        "billId": 107694
      },
      {
        "state": "JP",
        "billNumber": "504M60000F42001",
        "billId": 107938
      },
      {
        "state": "JP",
        "billNumber": "504M60001400001",
        "billId": 107940
      },
      {
        "state": "JP",
        "billNumber": "504M60007FFE001",
        "billId": 107937
      },
      {
        "state": "LV",
        "billNumber": "124707",
        "billId": 108422
      },
      {
        "state": "LV",
        "billNumber": "221378",
        "billId": 108420
      },
      {
        "state": "MX",
        "billNumber": "LGPGIR",
        "billId": 111332
      },
      {
        "state": "NJ",
        "billNumber": "S-3399",
        "billId": 104171
      },
      {
        "state": "NL",
        "billNumber": "BWBR0016038",
        "billId": 108255
      },
      {
        "state": "NL",
        "billNumber": "BWBR0024500",
        "billId": 108250
      },
      {
        "state": "PL",
        "billNumber": "DU/2008/1464",
        "billId": 108385
      },
      {
        "state": "PL",
        "billNumber": "DU/2016/1863",
        "billId": 108374
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/1834",
        "billId": 108343
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/573",
        "billId": 108376
      },
      {
        "state": "SE",
        "billNumber": "sfs-1998-808",
        "billId": 108318
      },
      {
        "state": "SI",
        "billNumber": "2015-01-1513",
        "billId": 108433
      },
      {
        "state": "SI",
        "billNumber": "2024-01-2498",
        "billId": 108435
      },
      {
        "state": "SK",
        "billNumber": "2015/373",
        "billId": 108425
      },
      {
        "state": "UK",
        "billNumber": "nisr/2020/285",
        "billId": 108144
      },
      {
        "state": "UK",
        "billNumber": "ssi/2000/451",
        "billId": 108136
      },
      {
        "state": "UK",
        "billNumber": "uksi/2000/3375",
        "billId": 108135
      },
      {
        "state": "UK",
        "billNumber": "uksi/2005/263",
        "billId": 108130
      },
      {
        "state": "UK",
        "billNumber": "uksi/2012/3082",
        "billId": 108126
      },
      {
        "state": "UK",
        "billNumber": "uksi/2023/1244",
        "billId": 108120
      },
      {
        "state": "UK",
        "billNumber": "uksi/2025/1369",
        "billId": 108119
      },
      {
        "state": "UY",
        "billNumber": "decretos/260-2007",
        "billId": 111335
      },
      {
        "state": "UY",
        "billNumber": "leyes/17849-2004",
        "billId": 111334
      },
      {
        "state": "CN",
        "billNumber": "ff8081818d736e08018d786bd28914b5",
        "billId": 108480
      },
      {
        "state": "EE",
        "billNumber": "918053",
        "billId": 108419
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2015-1762",
        "billId": 108269
      },
      {
        "state": "EU",
        "billNumber": "32025L1892",
        "billId": 107686
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000026863961",
        "billId": 108044
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000027947087",
        "billId": 108029
      },
      {
        "state": "ME",
        "billNumber": "LD-1541",
        "billId": 79534
      },
      {
        "state": "MN",
        "billNumber": "HF-4565",
        "billId": 1221
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-1001",
        "billId": 108290
      },
      {
        "state": "VT",
        "billNumber": "H-142",
        "billId": 72481
      },
      {
        "state": "VT",
        "billNumber": "S-217",
        "billId": 72345
      },
      {
        "state": "EU",
        "billNumber": "32023D2683",
        "billId": 107728
      },
      {
        "state": "SE",
        "billNumber": "sfs-2005-209",
        "billId": 108311
      },
      {
        "state": "ME",
        "billNumber": "LD-1423",
        "billId": 80310
      },
      {
        "state": "VT",
        "billNumber": "S-254",
        "billId": 81811
      },
      {
        "state": "EU",
        "billNumber": "32021R0770",
        "billId": 107582
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/1466",
        "billId": 108381
      },
      {
        "state": "BR",
        "billNumber": "_ato2007-2010/2010/lei/l12305.htm",
        "billId": 108332
      },
      {
        "state": "CA",
        "billNumber": "regulation/210391",
        "billId": 108593
      },
      {
        "state": "CL",
        "billNumber": "1208163",
        "billId": 108279
      },
      {
        "state": "CN",
        "billNumber": "zhengce/zhengceku/2008-03/28/content_2047.htm",
        "billId": 108499
      },
      {
        "state": "IN",
        "billNumber": "227293",
        "billId": 111391
      },
      {
        "state": "NY",
        "billNumber": "A-8195",
        "billId": 60357
      },
      {
        "state": "SE",
        "billNumber": "sfs-2011-927",
        "billId": 108301
      },
      {
        "state": "UK",
        "billNumber": "uksi/2017/1221",
        "billId": 108122
      },
      {
        "state": "CA",
        "billNumber": "regulation/200522",
        "billId": 108594
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000033691469",
        "billId": 107961
      },
      {
        "state": "CA",
        "billNumber": "449_2004_pit",
        "billId": 108588
      },
      {
        "state": "CN",
        "billNumber": "2c909fdd678bf17901678bf8bb110b8b",
        "billId": 108484
      },
      {
        "state": "CN",
        "billNumber": "zhengce/zhengceku/2021-02/22/content_5588274.htm",
        "billId": 108498
      },
      {
        "state": "CT",
        "billNumber": "HB-5352",
        "billId": 82680
      },
      {
        "state": "EU",
        "billNumber": "31999D0652",
        "billId": 107396
      },
      {
        "state": "EU",
        "billNumber": "32003D0082",
        "billId": 107541
      },
      {
        "state": "EU",
        "billNumber": "32004D0312",
        "billId": 107424
      },
      {
        "state": "EU",
        "billNumber": "32004D0486",
        "billId": 107448
      },
      {
        "state": "EU",
        "billNumber": "32008L0033",
        "billId": 107517
      },
      {
        "state": "EU",
        "billNumber": "32013R1257",
        "billId": 107348
      },
      {
        "state": "EU",
        "billNumber": "32019D0665",
        "billId": 107609
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000031056680",
        "billId": 107994
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047274648",
        "billId": 107848
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/149/made/en",
        "billId": 108322
      },
      {
        "state": "JP",
        "billNumber": "408M50000500001",
        "billId": 107874
      },
      {
        "state": "JP",
        "billNumber": "431M60001900001",
        "billId": 107935
      },
      {
        "state": "JP",
        "billNumber": "508AC0000000033",
        "billId": 107852
      },
      {
        "state": "MN",
        "billNumber": "HF-3320",
        "billId": 82543
      },
      {
        "state": "SE",
        "billNumber": "sfs-2018-1463",
        "billId": 108293
      },
      {
        "state": "UK",
        "billNumber": "uksi/1997/648",
        "billId": 108139
      },
      {
        "state": "UK",
        "billNumber": "uksi/2013/1857",
        "billId": 108125
      },
      {
        "state": "UK",
        "billNumber": "wsi/2011/551",
        "billId": 108196
      },
      {
        "state": "WA",
        "billNumber": "SB-5144",
        "billId": 104189
      },
      {
        "state": "EU",
        "billNumber": "32019D0638",
        "billId": 107572
      },
      {
        "state": "AT",
        "billNumber": "20002086",
        "billId": 108327
      },
      {
        "state": "NY",
        "billNumber": "S-10168",
        "billId": 79613
      },
      {
        "state": "CA",
        "billNumber": "SB-707",
        "billId": 620
      },
      {
        "state": "EU",
        "billNumber": "32019D2193",
        "billId": 107624
      },
      {
        "state": "EU",
        "billNumber": "32024R1252",
        "billId": 107704
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-27",
        "billId": 108113
      },
      {
        "state": "PE",
        "billNumber": "dl-1278",
        "billId": 111346
      },
      {
        "state": "WA",
        "billNumber": "SB-5284",
        "billId": 104217
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000019906779",
        "billId": 108031
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-23",
        "billId": 108108
      },
      {
        "state": "SE",
        "billNumber": "sfs-2023-133",
        "billId": 108283
      },
      {
        "state": "BR",
        "billNumber": "2599695",
        "billId": 111363
      },
      {
        "state": "AU",
        "billNumber": "F2011L02093",
        "billId": 108625
      },
      {
        "state": "AU",
        "billNumber": "F2021L00624",
        "billId": 108605
      },
      {
        "state": "CA",
        "billNumber": "AB-1311",
        "billId": 81168
      },
      {
        "state": "CL",
        "billNumber": "1090894",
        "billId": 108275
      },
      {
        "state": "CN",
        "billNumber": "ff8081817fd9834101804ef8f5bf71f5",
        "billId": 108473
      },
      {
        "state": "CN",
        "billNumber": "ff80818198a7ecd401994c3ed9ec259d",
        "billId": 108462
      },
      {
        "state": "DC",
        "billNumber": "D.C. Law 24-320",
        "billId": 104190
      },
      {
        "state": "EU",
        "billNumber": "32021D1384",
        "billId": 107619
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043327059",
        "billId": 107977
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000052450618",
        "billId": 107972
      },
      {
        "state": "JP",
        "billNumber": "407CO0000000411",
        "billId": 107858
      },
      {
        "state": "JP",
        "billNumber": "504M60001000001",
        "billId": 107939
      },
      {
        "state": "LT",
        "billNumber": "TAIS.325345",
        "billId": 108431
      },
      {
        "state": "MD",
        "billNumber": "SB-686",
        "billId": 72278
      },
      {
        "state": "ME",
        "billNumber": "LD-1519",
        "billId": 81678
      },
      {
        "state": "NL",
        "billNumber": "BWBR0045640",
        "billId": 108238
      },
      {
        "state": "NL",
        "billNumber": "BWBR0050381",
        "billId": 108236
      },
      {
        "state": "NY",
        "billNumber": "S-5663",
        "billId": 72875
      },
      {
        "state": "NY",
        "billNumber": "S-7552",
        "billId": 60359
      },
      {
        "state": "SE",
        "billNumber": "sfs-2000-208",
        "billId": 108313
      },
      {
        "state": "SE",
        "billNumber": "sfs-2007-186",
        "billId": 108308
      },
      {
        "state": "UK",
        "billNumber": "ssi/2002/147",
        "billId": 108134
      },
      {
        "state": "UK",
        "billNumber": "ssi/2009/247",
        "billId": 108160
      },
      {
        "state": "UK",
        "billNumber": "uksi/1999/1361",
        "billId": 108138
      },
      {
        "state": "UK",
        "billNumber": "uksi/2024/1332",
        "billId": 108115
      },
      {
        "state": "UK",
        "billNumber": "wsi/2002/813",
        "billId": 108132
      },
      {
        "state": "VT",
        "billNumber": "H-915",
        "billId": 1213
      },
      {
        "state": "PL",
        "billNumber": "DU/2013/1155",
        "billId": 108384
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127da36ca191c",
        "billId": 108448
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/1994/06/17/n4/jo/fr",
        "billId": 108415
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/1648",
        "billId": 108352
      },
      {
        "state": "BR",
        "billNumber": "2483680",
        "billId": 111360
      },
      {
        "state": "BR",
        "billNumber": "2512771",
        "billId": 111359
      },
      {
        "state": "BR",
        "billNumber": "2604703",
        "billId": 111355
      },
      {
        "state": "BR",
        "billNumber": "2623849",
        "billId": 111352
      },
      {
        "state": "BR",
        "billNumber": "_ato2019-2022/2022/decreto/D10936.htm",
        "billId": 108333
      },
      {
        "state": "CA",
        "billNumber": "200_2007",
        "billId": 108585
      },
      {
        "state": "CN",
        "billNumber": "zhengce/zhengceku/2010-12/31/content_5041.htm",
        "billId": 108502
      },
      {
        "state": "CO",
        "billNumber": "mads:resolucion-1407-de-2018",
        "billId": 111342
      },
      {
        "state": "EU",
        "billNumber": "32008L0098",
        "billId": 107264
      },
      {
        "state": "EU",
        "billNumber": "32009D0851",
        "billId": 107486
      },
      {
        "state": "EU",
        "billNumber": "32026D1435",
        "billId": 111297
      },
      {
        "state": "JP",
        "billNumber": "414CO0000000389",
        "billId": 107862
      },
      {
        "state": "JP",
        "billNumber": "419M60001200005",
        "billId": 107930
      },
      {
        "state": "JP",
        "billNumber": "507CO0000000003",
        "billId": 107866
      },
      {
        "state": "JP",
        "billNumber": "508M60001740001",
        "billId": 107955
      },
      {
        "state": "NY",
        "billNumber": "A-1209",
        "billId": 1444
      },
      {
        "state": "NY",
        "billNumber": "S-1460",
        "billId": 81668
      },
      {
        "state": "NY",
        "billNumber": "S-1463",
        "billId": 1424
      },
      {
        "state": "NY",
        "billNumber": "S-7553",
        "billId": 1162
      },
      {
        "state": "OR",
        "billNumber": "HB-3220",
        "billId": 80376
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/1403",
        "billId": 108356
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/779",
        "billId": 108353
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1587",
        "billId": 108344
      },
      {
        "state": "SE",
        "billNumber": "sfs-1998-902",
        "billId": 108315
      },
      {
        "state": "UK",
        "billNumber": "nisr/2009/159",
        "billId": 108161
      },
      {
        "state": "UK",
        "billNumber": "ukpga/2021/30",
        "billId": 108114
      },
      {
        "state": "UK",
        "billNumber": "uksi/2002/732",
        "billId": 108133
      },
      {
        "state": "UK",
        "billNumber": "uksi/2018/1214",
        "billId": 108146
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000019074839",
        "billId": 107968
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000022740348",
        "billId": 108034
      },
      {
        "state": "BR",
        "billNumber": "2629580",
        "billId": 111351
      },
      {
        "state": "CA",
        "billNumber": "statute/16r12",
        "billId": 108592
      },
      {
        "state": "EU",
        "billNumber": "32024R3230",
        "billId": 107745
      },
      {
        "state": "BR",
        "billNumber": "2314561",
        "billId": 111361
      },
      {
        "state": "CA",
        "billNumber": "AB-1857",
        "billId": 82616
      },
      {
        "state": "CT",
        "billNumber": "HB-6486",
        "billId": 82796
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000116",
        "billId": 107696
      },
      {
        "state": "OR",
        "billNumber": "SB-582",
        "billId": 72452
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/992",
        "billId": 108361
      },
      {
        "state": "PL",
        "billNumber": "DU/2022/699",
        "billId": 108349
      },
      {
        "state": "SE",
        "billNumber": "sfs-2014-1074",
        "billId": 108298
      },
      {
        "state": "UK",
        "billNumber": "ukpga/2003/29",
        "billId": 108183
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047439314",
        "billId": 107851
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000049889812",
        "billId": 107958
      },
      {
        "state": "EU",
        "billNumber": "32016D2323",
        "billId": 107279
      },
      {
        "state": "PE",
        "billNumber": "ds-009-2019-minam",
        "billId": 111348
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/21",
        "billId": 108362
      },
      {
        "state": "UK",
        "billNumber": "ssi/2023/160",
        "billId": 108156
      },
      {
        "state": "CL",
        "billNumber": "1154847",
        "billId": 108276
      },
      {
        "state": "RI",
        "billNumber": "HB-6207",
        "billId": 82640
      },
      {
        "state": "RI",
        "billNumber": "SB-996",
        "billId": 79521
      },
      {
        "state": "SE",
        "billNumber": "sfs-2025-813",
        "billId": 108285
      }
    ]
  },
  {
    "lever": "recycled_content",
    "name": "Recycled Content",
    "headline": "Incorporate post-consumer recycled content",
    "direction": "Incorporate minimum 25% post-consumer recycled plastic by 2026.",
    "focus": [
      "Packaging",
      "Electronics",
      "Textiles",
      "Batteries",
      "Organics",
      "Hazardous materials",
      "Vehicles"
    ],
    "billCount": 96,
    "states": [
      "AT",
      "BR",
      "CA",
      "CN",
      "CO",
      "DK",
      "EE",
      "ES",
      "EU",
      "FI",
      "FR",
      "IN",
      "JP",
      "LV",
      "ME",
      "MN",
      "NL",
      "NY",
      "OR",
      "PE",
      "PL",
      "SE",
      "SI",
      "UK",
      "VT"
    ],
    "evidence": {
      "state": "ME",
      "bill": "LD-1467",
      "quote": "Beginning January 1, 2026 through December 31, 2030: ensure that the total number of plastic beverage containers sold, offered for sale, or distributed for sale in Maine contain, on average and in the aggregate, at least 25% post-consumer recycled plastic"
    },
    "examples": [
      {
        "action": "Incorporate minimum 25% post-consumer recycled plastic by 2026.",
        "state": "ME",
        "billNumber": "LD-1467",
        "billId": 72366,
        "quote": "Beginning January 1, 2026 through December 31, 2030: ensure that the total number of plastic beverage containers sold, offered for sale, or distributed for sale in Maine contain, on average and in the aggregate, at least 25% post-consumer recycled plastic"
      },
      {
        "action": "Incorporate minimum 10% post-consumer recycled content in carpet.",
        "state": "NY",
        "billNumber": "S-5027C",
        "billId": 104184,
        "quote": "Ensure carpet sold in the state is manufactured with minimum 10% post-consumer content (effective two years after effective date)"
      },
      {
        "action": "Incorporate minimum 15% post-consumer recycled PET in bottles.",
        "state": "PE",
        "billNumber": "ley-30884",
        "billId": 111349,
        "quote": "Manufacturers of PET bottles for human consumption beverages, personal hygiene, and similar products must include at least 15% post-consumer recycled PET (PET-PCR) in their production chain, complying with food safety standards, within 3 years of publication."
      }
    ],
    "feeImpact": {
      "malus": true,
      "bonus": true,
      "setJurisdictions": [
        "BR",
        "ES",
        "EU",
        "FR",
        "JP",
        "LV",
        "PL",
        "UK"
      ],
      "usPending": true,
      "examples": []
    },
    "bills": [
      {
        "state": "ME",
        "billNumber": "LD-1467",
        "billId": 72366
      },
      {
        "state": "NY",
        "billNumber": "S-5027C",
        "billId": 104184
      },
      {
        "state": "PE",
        "billNumber": "ley-30884",
        "billId": 111349
      },
      {
        "state": "AT",
        "billNumber": "20008902",
        "billId": 108328
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/927",
        "billId": 108366
      },
      {
        "state": "CO",
        "billNumber": "HB-21-1162",
        "billId": 72433
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1658",
        "billId": 108368
      },
      {
        "state": "BR",
        "billNumber": "_ato2023-2026/2025/decreto/D12688.htm",
        "billId": 108335
      },
      {
        "state": "CA",
        "billNumber": "AB-661",
        "billId": 83365
      },
      {
        "state": "CA",
        "billNumber": "SB-1013",
        "billId": 851
      },
      {
        "state": "CA",
        "billNumber": "SB-303",
        "billId": 733
      },
      {
        "state": "CA",
        "billNumber": "SB-38",
        "billId": 82353
      },
      {
        "state": "CA",
        "billNumber": "SB-54",
        "billId": 865
      },
      {
        "state": "CN",
        "billNumber": "zhengce/content/2017-01/03/content_5156043.htm",
        "billId": 108496
      },
      {
        "state": "EU",
        "billNumber": "32008D0440",
        "billId": 107287
      },
      {
        "state": "EU",
        "billNumber": "32009D0292",
        "billId": 107529
      },
      {
        "state": "IN",
        "billNumber": "227249",
        "billId": 111387
      },
      {
        "state": "JP",
        "billNumber": "413M60000400059",
        "billId": 107892
      },
      {
        "state": "JP",
        "billNumber": "508M60000400007",
        "billId": 107946
      },
      {
        "state": "JP",
        "billNumber": "508M60000400008",
        "billId": 107948
      },
      {
        "state": "JP",
        "billNumber": "508M60000400009",
        "billId": 107947
      },
      {
        "state": "JP",
        "billNumber": "508M60000400010",
        "billId": 107951
      },
      {
        "state": "JP",
        "billNumber": "508M60000400011",
        "billId": 107949
      },
      {
        "state": "JP",
        "billNumber": "508M60000740002",
        "billId": 107953
      },
      {
        "state": "NL",
        "billNumber": "BWBR0018139",
        "billId": 108243
      },
      {
        "state": "SE",
        "billNumber": "sfs-2018-1462",
        "billId": 108294
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2022-5809",
        "billId": 108267
      },
      {
        "state": "MN",
        "billNumber": "HF-3911",
        "billId": 104216
      },
      {
        "state": "EU",
        "billNumber": "32025R0040",
        "billId": 107258
      },
      {
        "state": "JP",
        "billNumber": "413M60000400083",
        "billId": 107897
      },
      {
        "state": "EU",
        "billNumber": "32025R2269",
        "billId": 107759
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2025-17186",
        "billId": 108272
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047483124",
        "billId": 107806
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-18",
        "billId": 108106
      },
      {
        "state": "NY",
        "billNumber": "A-6193",
        "billId": 60356
      },
      {
        "state": "EU",
        "billNumber": "32023D2683",
        "billId": 107728
      },
      {
        "state": "EU",
        "billNumber": "32001D0171",
        "billId": 107357
      },
      {
        "state": "JP",
        "billNumber": "413M60000400088",
        "billId": 107901
      },
      {
        "state": "CN",
        "billNumber": "ff80818180e0a4410180f4acf8e12c02",
        "billId": 108472
      },
      {
        "state": "CN",
        "billNumber": "zhengce/zhengceku/2017-01/03/content_5156043.htm",
        "billId": 108497
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2006-9832",
        "billId": 108273
      },
      {
        "state": "EU",
        "billNumber": "32024L0232",
        "billId": 107559
      },
      {
        "state": "EU",
        "billNumber": "32024R1781",
        "billId": 107265
      },
      {
        "state": "FI",
        "billNumber": "2011/646",
        "billId": 108405
      },
      {
        "state": "JP",
        "billNumber": "403AC0000000048",
        "billId": 107692
      },
      {
        "state": "JP",
        "billNumber": "413M60000400079",
        "billId": 107881
      },
      {
        "state": "JP",
        "billNumber": "413M60000400080",
        "billId": 107903
      },
      {
        "state": "JP",
        "billNumber": "413M60000400082",
        "billId": 107899
      },
      {
        "state": "JP",
        "billNumber": "413M60000400085",
        "billId": 107900
      },
      {
        "state": "JP",
        "billNumber": "413M60000400086",
        "billId": 107902
      },
      {
        "state": "JP",
        "billNumber": "413M60000400089",
        "billId": 107898
      },
      {
        "state": "JP",
        "billNumber": "413M60000400090",
        "billId": 107890
      },
      {
        "state": "JP",
        "billNumber": "413M60000400091",
        "billId": 107888
      },
      {
        "state": "NL",
        "billNumber": "BWBR0013707",
        "billId": 108258
      },
      {
        "state": "NL",
        "billNumber": "BWBR0048093",
        "billId": 108233
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032847905",
        "billId": 107814
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-3",
        "billId": 108104
      },
      {
        "state": "OR",
        "billNumber": "HB-3780",
        "billId": 72412
      },
      {
        "state": "EU",
        "billNumber": "32002D0525",
        "billId": 107504
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000042592423",
        "billId": 107962
      },
      {
        "state": "EU",
        "billNumber": "32022R1616",
        "billId": 107638
      },
      {
        "state": "NL",
        "billNumber": "BWBR0048299",
        "billId": 108235
      },
      {
        "state": "BR",
        "billNumber": "2565302",
        "billId": 111365
      },
      {
        "state": "BR",
        "billNumber": "2599695",
        "billId": 111363
      },
      {
        "state": "CN",
        "billNumber": "ff808181799def980179ad26f28814aa",
        "billId": 108463
      },
      {
        "state": "CN",
        "billNumber": "ff808181927f12760194167453206544",
        "billId": 108467
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2021-5868",
        "billId": 108271
      },
      {
        "state": "EU",
        "billNumber": "32025R0351",
        "billId": 107713
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000049184670",
        "billId": 107816
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-12",
        "billId": 108102
      },
      {
        "state": "JP",
        "billNumber": "413M60000400087",
        "billId": 107896
      },
      {
        "state": "JP",
        "billNumber": "424AC0000000057",
        "billId": 107690
      },
      {
        "state": "JP",
        "billNumber": "506AC0000000041",
        "billId": 107853
      },
      {
        "state": "NY",
        "billNumber": "S-10168",
        "billId": 79613
      },
      {
        "state": "SI",
        "billNumber": "2021-01-1053",
        "billId": 108432
      },
      {
        "state": "BR",
        "billNumber": "2544402",
        "billId": 111367
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043458675",
        "billId": 107815
      },
      {
        "state": "ME",
        "billNumber": "LD-1541",
        "billId": 79534
      },
      {
        "state": "VT",
        "billNumber": "H-142",
        "billId": 72481
      },
      {
        "state": "DK",
        "billNumber": "lta/2025/1146",
        "billId": 108399
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000110",
        "billId": 107855
      },
      {
        "state": "NL",
        "billNumber": "BWBR0016038",
        "billId": 108255
      },
      {
        "state": "EU",
        "billNumber": "32025L1892",
        "billId": 107686
      },
      {
        "state": "VT",
        "billNumber": "H-915",
        "billId": 1213
      },
      {
        "state": "LV",
        "billNumber": "124707",
        "billId": 108422
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000052450618",
        "billId": 107972
      },
      {
        "state": "IN",
        "billNumber": "227293",
        "billId": 111391
      },
      {
        "state": "JP",
        "billNumber": "503AC0000000060",
        "billId": 107694
      },
      {
        "state": "NL",
        "billNumber": "BWBR0046477",
        "billId": 108260
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000104",
        "billId": 107697
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/2151",
        "billId": 108350
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127fab8a83b90",
        "billId": 108471
      },
      {
        "state": "EE",
        "billNumber": "749804",
        "billId": 108417
      },
      {
        "state": "UK",
        "billNumber": "uksi/2025/1369",
        "billId": 108119
      },
      {
        "state": "EU",
        "billNumber": "32024R1252",
        "billId": 107704
      },
      {
        "state": "UK",
        "billNumber": "ssi/2025/189",
        "billId": 108177
      }
    ]
  },
  {
    "lever": "source_reduction",
    "name": "Source Reduction",
    "headline": "Reduce packaging material per unit (lightweight, right-size)",
    "direction": "Design paper carryout bags with basis weight ≤30 pounds to escape bag fee requirements.",
    "focus": [
      "Packaging",
      "Organics",
      "Electronics",
      "Hazardous materials",
      "Batteries",
      "Textiles",
      "Construction"
    ],
    "billCount": 182,
    "states": [
      "AT",
      "AU",
      "BR",
      "CA",
      "CH",
      "CL",
      "CN",
      "CO",
      "CZ",
      "DE",
      "DK",
      "EE",
      "ES",
      "EU",
      "FI",
      "FR",
      "IN",
      "JP",
      "LT",
      "LU",
      "LV",
      "ME",
      "MN",
      "MX",
      "NL",
      "OR",
      "PE",
      "PL",
      "SE",
      "SI",
      "UK",
      "UY",
      "WA"
    ],
    "evidence": {
      "state": "CO",
      "bill": "HB-21-1162",
      "quote": "Bags with paper basis weight of 30 pounds or less are excluded from the definition of 'carryout bag'"
    },
    "examples": [
      {
        "action": "Design paper carryout bags with basis weight ≤30 pounds to escape bag fee requirements.",
        "state": "CO",
        "billNumber": "HB-21-1162",
        "billId": 72433,
        "quote": "Bags with paper basis weight of 30 pounds or less are excluded from the definition of 'carryout bag'"
      },
      {
        "action": "Achieve source reduction targets for covered plastic packaging.",
        "state": "CA",
        "billNumber": "SB-303",
        "billId": 733,
        "quote": "Achieve source reduction targets for covered plastic packaging"
      },
      {
        "action": "Reduce excessive packaging; comply with national mandatory standards.",
        "state": "CN",
        "billNumber": "4028abcc61277793016127c954530a34",
        "billId": 108446,
        "quote": "Prohibit excessive packaging that violates national mandatory standards"
      }
    ],
    "feeImpact": {
      "malus": true,
      "bonus": true,
      "setJurisdictions": [
        "AU",
        "CH",
        "CL",
        "DK",
        "EE",
        "ES",
        "EU",
        "FR",
        "PE",
        "PL",
        "SE",
        "UK"
      ],
      "usPending": true,
      "examples": [
        {
          "jurisdiction": "ES",
          "amount": "0.45 eur/kg non recycled"
        },
        {
          "jurisdiction": "FR",
          "amount": "0.15 euros/kilogram"
        }
      ]
    },
    "bills": [
      {
        "state": "CO",
        "billNumber": "HB-21-1162",
        "billId": 72433
      },
      {
        "state": "CA",
        "billNumber": "SB-303",
        "billId": 733
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127c954530a34",
        "billId": 108446
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127e112bb1ff4",
        "billId": 108449
      },
      {
        "state": "CN",
        "billNumber": "ff80818180e0a4410180f4acf8e12c02",
        "billId": 108472
      },
      {
        "state": "CN",
        "billNumber": "ff8081818d736e08018d786bd28914b5",
        "billId": 108480
      },
      {
        "state": "EE",
        "billNumber": "113032019103",
        "billId": 108418
      },
      {
        "state": "EU",
        "billNumber": "32021R1929",
        "billId": 107621
      },
      {
        "state": "EU",
        "billNumber": "32025R0040",
        "billId": 107258
      },
      {
        "state": "FI",
        "billNumber": "2011/646",
        "billId": 108405
      },
      {
        "state": "FI",
        "billNumber": "2021/714",
        "billId": 108406
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043458675",
        "billId": 107815
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-11",
        "billId": 108092
      },
      {
        "state": "JP",
        "billNumber": "407AC0000000112",
        "billId": 107693
      },
      {
        "state": "JP",
        "billNumber": "413M60000400062",
        "billId": 107908
      },
      {
        "state": "JP",
        "billNumber": "413M60000400063",
        "billId": 107906
      },
      {
        "state": "JP",
        "billNumber": "413M60000400064",
        "billId": 107912
      },
      {
        "state": "JP",
        "billNumber": "413M60000400065",
        "billId": 107909
      },
      {
        "state": "JP",
        "billNumber": "413M60000400066",
        "billId": 107911
      },
      {
        "state": "JP",
        "billNumber": "413M60000400067",
        "billId": 107905
      },
      {
        "state": "JP",
        "billNumber": "413M60000400068",
        "billId": 107910
      },
      {
        "state": "JP",
        "billNumber": "413M60000400069",
        "billId": 107907
      },
      {
        "state": "JP",
        "billNumber": "413M60000400070",
        "billId": 107886
      },
      {
        "state": "JP",
        "billNumber": "413M60000400071",
        "billId": 107878
      },
      {
        "state": "JP",
        "billNumber": "413M60000400072",
        "billId": 107882
      },
      {
        "state": "JP",
        "billNumber": "413M60000400073",
        "billId": 107880
      },
      {
        "state": "JP",
        "billNumber": "413M60000400074",
        "billId": 107887
      },
      {
        "state": "JP",
        "billNumber": "413M60000400075",
        "billId": 107883
      },
      {
        "state": "JP",
        "billNumber": "413M60000C00004",
        "billId": 107914
      },
      {
        "state": "JP",
        "billNumber": "504M60007FFE001",
        "billId": 107937
      },
      {
        "state": "LT",
        "billNumber": "TAIS.161216",
        "billId": 108429
      },
      {
        "state": "NL",
        "billNumber": "BWBR0018139",
        "billId": 108243
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/542",
        "billId": 108371
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/160",
        "billId": 108369
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/927",
        "billId": 108366
      },
      {
        "state": "SE",
        "billNumber": "sfs-2018-1462",
        "billId": 108294
      },
      {
        "state": "UY",
        "billNumber": "leyes/19829-2019",
        "billId": 111336
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-18",
        "billId": 108106
      },
      {
        "state": "ME",
        "billNumber": "LD-1541",
        "billId": 79534
      },
      {
        "state": "MN",
        "billNumber": "HF-3911",
        "billId": 104216
      },
      {
        "state": "CN",
        "billNumber": "2c909fdd678bf17901678bf737800631",
        "billId": 108442
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2022-5809",
        "billId": 108267
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016128016d2f42e7",
        "billId": 108445
      },
      {
        "state": "CN",
        "billNumber": "ff808081752b7d430176b1a842ea3f28",
        "billId": 108476
      },
      {
        "state": "CN",
        "billNumber": "zhengce/zhengceku/2017-01/03/content_5156043.htm",
        "billId": 108497
      },
      {
        "state": "EU",
        "billNumber": "32004L0012",
        "billId": 107378
      },
      {
        "state": "EU",
        "billNumber": "32018L0852",
        "billId": 107472
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-17",
        "billId": 108099
      },
      {
        "state": "JP",
        "billNumber": "413M60000400076",
        "billId": 107885
      },
      {
        "state": "JP",
        "billNumber": "413M60000400088",
        "billId": 107901
      },
      {
        "state": "JP",
        "billNumber": "413M60000400090",
        "billId": 107890
      },
      {
        "state": "JP",
        "billNumber": "413M60000400091",
        "billId": 107888
      },
      {
        "state": "JP",
        "billNumber": "413M60001F40004",
        "billId": 107921
      },
      {
        "state": "PL",
        "billNumber": "DU/2013/888",
        "billId": 108375
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/150",
        "billId": 108372
      },
      {
        "state": "PL",
        "billNumber": "DU/2020/1114",
        "billId": 108370
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1658",
        "billId": 108368
      },
      {
        "state": "SE",
        "billNumber": "sfs-1997-185",
        "billId": 108320
      },
      {
        "state": "AT",
        "billNumber": "20008902",
        "billId": 108328
      },
      {
        "state": "NL",
        "billNumber": "BWBR0037392",
        "billId": 108241
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000044036494",
        "billId": 107999
      },
      {
        "state": "CN",
        "billNumber": "ff8080816f135f46016f1d06082912c2",
        "billId": 108441
      },
      {
        "state": "CN",
        "billNumber": "ff8081818364d903018407f6c4887544",
        "billId": 108461
      },
      {
        "state": "CN",
        "billNumber": "ff808181865edc140186d8920a3423b2",
        "billId": 108478
      },
      {
        "state": "CN",
        "billNumber": "ff808181927f127601936667b5d41015",
        "billId": 108465
      },
      {
        "state": "DE",
        "billNumber": "krwg",
        "billId": 108221
      },
      {
        "state": "DK",
        "billNumber": "lta/2019/1218",
        "billId": 108404
      },
      {
        "state": "EU",
        "billNumber": "31994L0062",
        "billId": 107262
      },
      {
        "state": "IN",
        "billNumber": "183721",
        "billId": 111386
      },
      {
        "state": "JP",
        "billNumber": "418M60000740001",
        "billId": 107928
      },
      {
        "state": "SE",
        "billNumber": "sfs-1998-808",
        "billId": 108318
      },
      {
        "state": "CA",
        "billNumber": "regulation/200522",
        "billId": 108594
      },
      {
        "state": "CL",
        "billNumber": "1208163",
        "billId": 108279
      },
      {
        "state": "EU",
        "billNumber": "32015L0720",
        "billId": 107334
      },
      {
        "state": "EU",
        "billNumber": "32020R2151",
        "billId": 107601
      },
      {
        "state": "IN",
        "billNumber": "227249",
        "billId": 111387
      },
      {
        "state": "PL",
        "billNumber": "DU/2008/1464",
        "billId": 108385
      },
      {
        "state": "DE",
        "billNumber": "ewkfondsg",
        "billId": 108223
      },
      {
        "state": "EE",
        "billNumber": "918053",
        "billId": 108419
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-3",
        "billId": 108104
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047483124",
        "billId": 107806
      },
      {
        "state": "JP",
        "billNumber": "413M60000400080",
        "billId": 107903
      },
      {
        "state": "SE",
        "billNumber": "sfs-2014-1073",
        "billId": 108299
      },
      {
        "state": "JP",
        "billNumber": "413M60000740001",
        "billId": 107916
      },
      {
        "state": "EU",
        "billNumber": "32023D2683",
        "billId": 107728
      },
      {
        "state": "AT",
        "billNumber": "20002086",
        "billId": 108327
      },
      {
        "state": "BR",
        "billNumber": "_ato2007-2010/2010/lei/l12305.htm",
        "billId": 108332
      },
      {
        "state": "CA",
        "billNumber": "SB-54",
        "billId": 865
      },
      {
        "state": "CN",
        "billNumber": "ff80808175265dd40176b843949f3d0c",
        "billId": 108475
      },
      {
        "state": "CN",
        "billNumber": "ff8081818b6b80c1018b6f0b15700b8e",
        "billId": 108468
      },
      {
        "state": "CN",
        "billNumber": "ff808181927f0931019325530cb6751c",
        "billId": 108464
      },
      {
        "state": "CN",
        "billNumber": "zhengce/content/2017-01/03/content_5156043.htm",
        "billId": 108496
      },
      {
        "state": "CN",
        "billNumber": "zhengce/zhengceku/2008-03/28/content_2047.htm",
        "billId": 108499
      },
      {
        "state": "CN",
        "billNumber": "zhengce/zhengceku/2021-02/22/content_5588274.htm",
        "billId": 108498
      },
      {
        "state": "CZ",
        "billNumber": "2020/541",
        "billId": 108438
      },
      {
        "state": "EU",
        "billNumber": "32024R1781",
        "billId": 107265
      },
      {
        "state": "JP",
        "billNumber": "403AC0000000048",
        "billId": 107692
      },
      {
        "state": "JP",
        "billNumber": "504CO0000000025",
        "billId": 107865
      },
      {
        "state": "LT",
        "billNumber": "TAIS.59267",
        "billId": 108428
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/1994/06/17/n4/jo/fr",
        "billId": 108415
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/2017/03/21/a330/jo/fr",
        "billId": 108412
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/rgd/2018/07/02/a562/jo/fr",
        "billId": 108416
      },
      {
        "state": "LV",
        "billNumber": "57207",
        "billId": 108421
      },
      {
        "state": "CA",
        "billNumber": "AB-863",
        "billId": 79950
      },
      {
        "state": "JP",
        "billNumber": "408M50000500001",
        "billId": 107874
      },
      {
        "state": "SE",
        "billNumber": "sfs-2016-1041",
        "billId": 108296
      },
      {
        "state": "CH",
        "billNumber": "cc/2001/359",
        "billId": 108341
      },
      {
        "state": "DE",
        "billNumber": "ewkfondsv",
        "billId": 108231
      },
      {
        "state": "EU",
        "billNumber": "32018D0896",
        "billId": 107574
      },
      {
        "state": "EU",
        "billNumber": "32022D0162",
        "billId": 107613
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000000645543",
        "billId": 108040
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000019906779",
        "billId": 108031
      },
      {
        "state": "CL",
        "billNumber": "1157019",
        "billId": 108277
      },
      {
        "state": "MX",
        "billNumber": "LGPGIR",
        "billId": 111332
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2024-21709",
        "billId": 108274
      },
      {
        "state": "CN",
        "billNumber": "2c909fdd678bf17901678bf8bb110b8b",
        "billId": 108484
      },
      {
        "state": "CN",
        "billNumber": "ff808181799def980179ad26f28814aa",
        "billId": 108463
      },
      {
        "state": "CN",
        "billNumber": "ff808181927f12760194167453206544",
        "billId": 108467
      },
      {
        "state": "DK",
        "billNumber": "lta/2025/1146",
        "billId": 108399
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-12",
        "billId": 108102
      },
      {
        "state": "JP",
        "billNumber": "503AC0000000060",
        "billId": 107694
      },
      {
        "state": "SI",
        "billNumber": "2015-01-1513",
        "billId": 108433
      },
      {
        "state": "UY",
        "billNumber": "leyes/17849-2004",
        "billId": 111334
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000031056680",
        "billId": 107994
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-1001",
        "billId": 108290
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127d5c1e814c1",
        "billId": 108477
      },
      {
        "state": "EU",
        "billNumber": "32013R1257",
        "billId": 107348
      },
      {
        "state": "SE",
        "billNumber": "sfs-1997-788",
        "billId": 108319
      },
      {
        "state": "CA",
        "billNumber": "statute/16r12",
        "billId": 108592
      },
      {
        "state": "CN",
        "billNumber": "ff80818198a7ecd401994c3ed9ec259d",
        "billId": 108462
      },
      {
        "state": "CO",
        "billNumber": "HB-22-1355",
        "billId": 72416
      },
      {
        "state": "EU",
        "billNumber": "31999D0042",
        "billId": 107452
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000033691469",
        "billId": 107961
      },
      {
        "state": "JP",
        "billNumber": "345AC0000000137",
        "billId": 107854
      },
      {
        "state": "JP",
        "billNumber": "407CO0000000411",
        "billId": 107858
      },
      {
        "state": "JP",
        "billNumber": "418M60000740002",
        "billId": 107929
      },
      {
        "state": "UK",
        "billNumber": "nisr/2020/285",
        "billId": 108144
      },
      {
        "state": "EU",
        "billNumber": "32013L0002",
        "billId": 107308
      },
      {
        "state": "CL",
        "billNumber": "1090894",
        "billId": 108275
      },
      {
        "state": "DK",
        "billNumber": "lta/2025/882",
        "billId": 108400
      },
      {
        "state": "CL",
        "billNumber": "1223902",
        "billId": 108278
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032847905",
        "billId": 107814
      },
      {
        "state": "UK",
        "billNumber": "uksi/2020/904",
        "billId": 108143
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127da36ca191c",
        "billId": 108448
      },
      {
        "state": "PE",
        "billNumber": "ds-014-2017-minam",
        "billId": 111347
      },
      {
        "state": "UK",
        "billNumber": "nisr/2023/25",
        "billId": 108158
      },
      {
        "state": "UK",
        "billNumber": "asp/2024/13",
        "billId": 108140
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000022740348",
        "billId": 108034
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/2151",
        "billId": 108350
      },
      {
        "state": "BR",
        "billNumber": "_ato2023-2026/2025/decreto/D12688.htm",
        "billId": 108335
      },
      {
        "state": "CA",
        "billNumber": "449_2004_pit",
        "billId": 108588
      },
      {
        "state": "EU",
        "billNumber": "32008L0098",
        "billId": 107264
      },
      {
        "state": "JP",
        "billNumber": "407M50000100061",
        "billId": 107871
      },
      {
        "state": "SE",
        "billNumber": "sfs-1998-902",
        "billId": 108315
      },
      {
        "state": "UK",
        "billNumber": "ssi/2025/10",
        "billId": 108142
      },
      {
        "state": "PE",
        "billNumber": "dl-1278",
        "billId": 111346
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000116",
        "billId": 107696
      },
      {
        "state": "EU",
        "billNumber": "32011D0677",
        "billId": 107525
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-23",
        "billId": 108108
      },
      {
        "state": "EU",
        "billNumber": "32025L1892",
        "billId": 107686
      },
      {
        "state": "LV",
        "billNumber": "221378",
        "billId": 108420
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/779",
        "billId": 108353
      },
      {
        "state": "BR",
        "billNumber": "2512771",
        "billId": 111359
      },
      {
        "state": "BR",
        "billNumber": "_ato2019-2022/2022/decreto/D10936.htm",
        "billId": 108333
      },
      {
        "state": "CA",
        "billNumber": "AB-1857",
        "billId": 82616
      },
      {
        "state": "EU",
        "billNumber": "31999L0031",
        "billId": 107296
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000029374870",
        "billId": 108026
      },
      {
        "state": "JP",
        "billNumber": "504M60001000001",
        "billId": 107939
      },
      {
        "state": "NL",
        "billNumber": "BWBR0050381",
        "billId": 108236
      },
      {
        "state": "CA",
        "billNumber": "AB-1311",
        "billId": 81168
      },
      {
        "state": "JP",
        "billNumber": "419M60001200005",
        "billId": 107930
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/1403",
        "billId": 108356
      },
      {
        "state": "EU",
        "billNumber": "32017D1508",
        "billId": 107278
      },
      {
        "state": "NL",
        "billNumber": "BWBR0045640",
        "billId": 108238
      },
      {
        "state": "OR",
        "billNumber": "HB-3780",
        "billId": 72412
      },
      {
        "state": "UK",
        "billNumber": "uksi/2024/1332",
        "billId": 108115
      },
      {
        "state": "WA",
        "billNumber": "SB-5284",
        "billId": 104217
      },
      {
        "state": "EU",
        "billNumber": "31999D0652",
        "billId": 107396
      },
      {
        "state": "PL",
        "billNumber": "DU/2022/699",
        "billId": 108349
      },
      {
        "state": "OR",
        "billNumber": "SB-582",
        "billId": 72452
      },
      {
        "state": "AU",
        "billNumber": "act-2011-031",
        "billId": 108640
      },
      {
        "state": "CN",
        "billNumber": "ff80818194a5cf290194da1c80c547bb",
        "billId": 108481
      }
    ]
  },
  {
    "lever": "reuse_refill",
    "name": "Reuse & Refill",
    "headline": "Shift to reusable / refillable formats",
    "direction": "Replace single-use bags with reusable or alternative bag designs.",
    "focus": [
      "Packaging",
      "Electronics",
      "Textiles",
      "Batteries",
      "Organics",
      "Hazardous materials",
      "Furniture"
    ],
    "billCount": 106,
    "states": [
      "AT",
      "AU",
      "BR",
      "CA",
      "CH",
      "CL",
      "CN",
      "CO",
      "CT",
      "CZ",
      "DE",
      "DK",
      "EE",
      "ES",
      "EU",
      "FI",
      "FR",
      "IE",
      "IN",
      "JP",
      "LT",
      "ME",
      "MN",
      "MX",
      "NL",
      "NY",
      "OR",
      "PE",
      "PL",
      "SE",
      "UK",
      "UY",
      "WA"
    ],
    "evidence": {
      "state": "PE",
      "bill": "ley-30884",
      "quote": "Supermarkets, self-service stores, warehouses, and general commercial establishments must progressively replace non-reusable polymeric bags with reusable bags or alternatives within 36 months of the law's entry into force."
    },
    "examples": [
      {
        "action": "Replace single-use bags with reusable or alternative bag designs.",
        "state": "PE",
        "billNumber": "ley-30884",
        "billId": 111349,
        "quote": "Supermarkets, self-service stores, warehouses, and general commercial establishments must progressively replace non-reusable polymeric bags with reusable bags or alternatives within 36 months of the law's entry into force."
      },
      {
        "action": "Design reusable carryout bags meeting durability and capacity specs to escape fees.",
        "state": "CO",
        "billNumber": "HB-21-1162",
        "billId": 72433,
        "quote": "Reusable carryout bags (designed/manufactured for at least 125 uses, carry at least 22 lbs over 175 feet, stitched handles, made of cloth/fiber/fabric or recycled material such as PET) are excluded from 'single-use plastic carryout bag' definition"
      },
      {
        "action": "Design containers for refill or ensure refillable alternatives available.",
        "state": "CA",
        "billNumber": "406_97_pit",
        "billId": 108587,
        "quote": "Only offer for sale or sell beverages in containers that can be refilled or recycled"
      }
    ],
    "feeImpact": {
      "malus": false,
      "bonus": true,
      "setJurisdictions": [
        "ES",
        "EU",
        "FI",
        "FR",
        "NL",
        "PL",
        "SE",
        "UK"
      ],
      "usPending": true,
      "examples": []
    },
    "bills": [
      {
        "state": "PE",
        "billNumber": "ley-30884",
        "billId": 111349
      },
      {
        "state": "CO",
        "billNumber": "HB-21-1162",
        "billId": 72433
      },
      {
        "state": "CA",
        "billNumber": "406_97_pit",
        "billId": 108587
      },
      {
        "state": "CA",
        "billNumber": "AB-962",
        "billId": 79926
      },
      {
        "state": "CT",
        "billNumber": "HB-5142",
        "billId": 82844
      },
      {
        "state": "EU",
        "billNumber": "32026D0429",
        "billId": 107775
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000026863961",
        "billId": 108044
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032770063",
        "billId": 108043
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000053625694",
        "billId": 107832
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-22",
        "billId": 108109
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-24",
        "billId": 108110
      },
      {
        "state": "IE",
        "billNumber": "eli/2007/si/798/made/en",
        "billId": 108326
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/282/made/en",
        "billId": 108324
      },
      {
        "state": "NL",
        "billNumber": "BWBR0048093",
        "billId": 108233
      },
      {
        "state": "CL",
        "billNumber": "1157019",
        "billId": 108277
      },
      {
        "state": "DE",
        "billNumber": "ewkfondsg",
        "billId": 108223
      },
      {
        "state": "JP",
        "billNumber": "418M60000740001",
        "billId": 107928
      },
      {
        "state": "DE",
        "billNumber": "battdg",
        "billId": 108220
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-3",
        "billId": 108104
      },
      {
        "state": "MN",
        "billNumber": "HF-3911",
        "billId": 104216
      },
      {
        "state": "AT",
        "billNumber": "20008902",
        "billId": 108328
      },
      {
        "state": "EU",
        "billNumber": "32025R0040",
        "billId": 107258
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043458675",
        "billId": 107815
      },
      {
        "state": "EU",
        "billNumber": "32018L0852",
        "billId": 107472
      },
      {
        "state": "CN",
        "billNumber": "ff808181927f127601936667b5d41015",
        "billId": 108465
      },
      {
        "state": "EU",
        "billNumber": "32024R1781",
        "billId": 107265
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000050749111",
        "billId": 107841
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/927",
        "billId": 108366
      },
      {
        "state": "SE",
        "billNumber": "sfs-2014-1073",
        "billId": 108299
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-999",
        "billId": 108286
      },
      {
        "state": "UK",
        "billNumber": "uksi/1999/3447",
        "billId": 108137
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2025-17186",
        "billId": 108272
      },
      {
        "state": "NL",
        "billNumber": "BWBR0044197",
        "billId": 108234
      },
      {
        "state": "BR",
        "billNumber": "_ato2023-2026/2025/decreto/D12688.htm",
        "billId": 108335
      },
      {
        "state": "CH",
        "billNumber": "cc/2000/299",
        "billId": 108340
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-17",
        "billId": 108099
      },
      {
        "state": "NL",
        "billNumber": "BWBR0048299",
        "billId": 108235
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1852",
        "billId": 108367
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/1911",
        "billId": 108365
      },
      {
        "state": "SE",
        "billNumber": "sfs-2006-1273",
        "billId": 108309
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2024-21709",
        "billId": 108274
      },
      {
        "state": "EU",
        "billNumber": "32012L0019",
        "billId": 107259
      },
      {
        "state": "DK",
        "billNumber": "lta/2025/1146",
        "billId": 108399
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-18",
        "billId": 108106
      },
      {
        "state": "JP",
        "billNumber": "403AC0000000048",
        "billId": 107692
      },
      {
        "state": "PL",
        "billNumber": "DU/2013/888",
        "billId": 108375
      },
      {
        "state": "SE",
        "billNumber": "sfs-1997-185",
        "billId": 108320
      },
      {
        "state": "FI",
        "billNumber": "2021/1029",
        "billId": 108409
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/2151",
        "billId": 108350
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2022-5809",
        "billId": 108267
      },
      {
        "state": "AT",
        "billNumber": "20002086",
        "billId": 108327
      },
      {
        "state": "CA",
        "billNumber": "SB-1143",
        "billId": 83174
      },
      {
        "state": "CN",
        "billNumber": "ff80818180e0a4410180f4acf8e12c02",
        "billId": 108472
      },
      {
        "state": "CN",
        "billNumber": "ff808181927f0931019325530cb6751c",
        "billId": 108464
      },
      {
        "state": "EE",
        "billNumber": "113032019103",
        "billId": 108418
      },
      {
        "state": "EU",
        "billNumber": "32001D0524",
        "billId": 107336
      },
      {
        "state": "EU",
        "billNumber": "32019D0665",
        "billId": 107609
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10",
        "billId": 108100
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-11",
        "billId": 108092
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-5",
        "billId": 108103
      },
      {
        "state": "JP",
        "billNumber": "407AC0000000112",
        "billId": 107693
      },
      {
        "state": "NL",
        "billNumber": "BWBR0046477",
        "billId": 108260
      },
      {
        "state": "NY",
        "billNumber": "A-8195",
        "billId": 60357
      },
      {
        "state": "UK",
        "billNumber": "nisr/2023/106",
        "billId": 108157
      },
      {
        "state": "UK",
        "billNumber": "ssi/2020/154",
        "billId": 108182
      },
      {
        "state": "UY",
        "billNumber": "leyes/19829-2019",
        "billId": 111336
      },
      {
        "state": "EU",
        "billNumber": "32005D0270",
        "billId": 107391
      },
      {
        "state": "UK",
        "billNumber": "uksi/2024/1332",
        "billId": 108115
      },
      {
        "state": "EU",
        "billNumber": "31994L0062",
        "billId": 107262
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-1001",
        "billId": 108290
      },
      {
        "state": "UY",
        "billNumber": "leyes/17849-2004",
        "billId": 111334
      },
      {
        "state": "DK",
        "billNumber": "lta/2025/882",
        "billId": 108400
      },
      {
        "state": "EU",
        "billNumber": "31999D0042",
        "billId": 107452
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000049184670",
        "billId": 107816
      },
      {
        "state": "MX",
        "billNumber": "LGPGIR",
        "billId": 111332
      },
      {
        "state": "CZ",
        "billNumber": "2020/541",
        "billId": 108438
      },
      {
        "state": "UK",
        "billNumber": "nisr/2020/285",
        "billId": 108144
      },
      {
        "state": "ME",
        "billNumber": "LD-1909",
        "billId": 83470
      },
      {
        "state": "BR",
        "billNumber": "_ato2007-2010/2010/lei/l12305.htm",
        "billId": 108332
      },
      {
        "state": "DE",
        "billNumber": "krwg",
        "billId": 108221
      },
      {
        "state": "LT",
        "billNumber": "TAIS.161216",
        "billId": 108429
      },
      {
        "state": "NL",
        "billNumber": "BWBR0045640",
        "billId": 108238
      },
      {
        "state": "EU",
        "billNumber": "31999D0823",
        "billId": 107276
      },
      {
        "state": "PE",
        "billNumber": "ds-014-2017-minam",
        "billId": 111347
      },
      {
        "state": "UK",
        "billNumber": "nisr/2023/25",
        "billId": 108158
      },
      {
        "state": "EU",
        "billNumber": "32015L0720",
        "billId": 107334
      },
      {
        "state": "EU",
        "billNumber": "32018L0851",
        "billId": 107294
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000042575740",
        "billId": 107805
      },
      {
        "state": "UK",
        "billNumber": "uksi/2020/904",
        "billId": 108143
      },
      {
        "state": "BR",
        "billNumber": "2512771",
        "billId": 111359
      },
      {
        "state": "EU",
        "billNumber": "32026D1435",
        "billId": 111297
      },
      {
        "state": "EU",
        "billNumber": "32013L0002",
        "billId": 107308
      },
      {
        "state": "OR",
        "billNumber": "SB-582",
        "billId": 72452
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/160",
        "billId": 108369
      },
      {
        "state": "CA",
        "billNumber": "449_2004_pit",
        "billId": 108588
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-27",
        "billId": 108113
      },
      {
        "state": "UK",
        "billNumber": "asp/2024/13",
        "billId": 108140
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047274648",
        "billId": 107848
      },
      {
        "state": "WA",
        "billNumber": "SB-5284",
        "billId": 104217
      },
      {
        "state": "EU",
        "billNumber": "32023R0595",
        "billId": 107683
      },
      {
        "state": "IN",
        "billNumber": "227293",
        "billId": 111391
      },
      {
        "state": "AU",
        "billNumber": "act-2011-031",
        "billId": 108640
      },
      {
        "state": "CA",
        "billNumber": "SB-560",
        "billId": 720
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/779",
        "billId": 108353
      },
      {
        "state": "UK",
        "billNumber": "ssi/2023/160",
        "billId": 108156
      },
      {
        "state": "PL",
        "billNumber": "DU/2022/699",
        "billId": 108349
      }
    ]
  },
  {
    "lever": "toxics_elimination",
    "name": "Toxics Elimination",
    "headline": "Eliminate restricted substances (PFAS, heavy metals, etc.)",
    "direction": "Do not intentionally add mercury to any product.",
    "focus": [
      "Packaging",
      "Electronics",
      "Hazardous materials",
      "Batteries",
      "Organics",
      "Vehicles",
      "Textiles"
    ],
    "billCount": 248,
    "states": [
      "AT",
      "AU",
      "BR",
      "CA",
      "CH",
      "CL",
      "CN",
      "CO",
      "CT",
      "CZ",
      "DC",
      "DE",
      "DK",
      "EE",
      "ES",
      "EU",
      "FI",
      "FR",
      "IE",
      "IN",
      "JP",
      "KY",
      "LT",
      "LU",
      "LV",
      "MD",
      "ME",
      "MN",
      "NL",
      "NY",
      "OR",
      "PE",
      "PL",
      "SE",
      "SI",
      "SK",
      "UK",
      "VT",
      "WA"
    ],
    "evidence": {
      "state": "AU",
      "bill": "F2021L01393",
      "quote": "Absolute prohibition on manufacture of mercury-added products"
    },
    "examples": [
      {
        "action": "Do not intentionally add mercury to any product.",
        "state": "AU",
        "billNumber": "F2021L01393",
        "billId": 108607,
        "quote": "Absolute prohibition on manufacture of mercury-added products"
      },
      {
        "action": "Ensure batteries contain ≤0.0005 wt% mercury regardless of form.",
        "state": "AT",
        "billNumber": "20005815",
        "billId": 108330,
        "quote": "do not place on market batteries containing more than 0.0005 wt% mercury (regardless of whether built into devices)"
      },
      {
        "action": "Remove lead, mercury, cadmium, hexavalent chromium, PBB, PBDE from EEE.",
        "state": "EU",
        "billNumber": "32011L0065",
        "billId": 107355,
        "quote": "Ensure EEE placed on the market does not contain restricted hazardous substances above maximum concentration values (Annex II)"
      }
    ],
    "feeImpact": {
      "malus": true,
      "bonus": true,
      "setJurisdictions": [
        "AU",
        "ES",
        "EU",
        "FR",
        "NL",
        "UK"
      ],
      "usPending": true,
      "examples": []
    },
    "bills": [
      {
        "state": "AU",
        "billNumber": "F2021L01393",
        "billId": 108607
      },
      {
        "state": "AT",
        "billNumber": "20005815",
        "billId": 108330
      },
      {
        "state": "EU",
        "billNumber": "32011L0065",
        "billId": 107355
      },
      {
        "state": "NL",
        "billNumber": "BWBR0024492",
        "billId": 108251
      },
      {
        "state": "NY",
        "billNumber": "S-5027C",
        "billId": 104184
      },
      {
        "state": "EU",
        "billNumber": "32009L0001",
        "billId": 107386
      },
      {
        "state": "JP",
        "billNumber": "413M60000400086",
        "billId": 107902
      },
      {
        "state": "LV",
        "billNumber": "57207",
        "billId": 108421
      },
      {
        "state": "NL",
        "billNumber": "BWBR0018139",
        "billId": 108243
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/542",
        "billId": 108371
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/927",
        "billId": 108366
      },
      {
        "state": "EU",
        "billNumber": "32006L0066",
        "billId": 107349
      },
      {
        "state": "EU",
        "billNumber": "32009R0767",
        "billId": 107456
      },
      {
        "state": "AT",
        "billNumber": "20008902",
        "billId": 108328
      },
      {
        "state": "JP",
        "billNumber": "413M60000400083",
        "billId": 107897
      },
      {
        "state": "CL",
        "billNumber": "1223902",
        "billId": 108278
      },
      {
        "state": "CN",
        "billNumber": "2c909fdd678bf17901678bf737800631",
        "billId": 108442
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127e112bb1ff4",
        "billId": 108449
      },
      {
        "state": "CN",
        "billNumber": "ff8080816f135f46016f1d06082912c2",
        "billId": 108441
      },
      {
        "state": "CN",
        "billNumber": "ff808081752b7d430176b1a842ea3f28",
        "billId": 108476
      },
      {
        "state": "CN",
        "billNumber": "ff8081817fc0f0f0017fd4fae0a7133e",
        "billId": 108450
      },
      {
        "state": "CN",
        "billNumber": "ff808181865edc140186d8920a3423b2",
        "billId": 108478
      },
      {
        "state": "DE",
        "billNumber": "altholzv",
        "billId": 108227
      },
      {
        "state": "DK",
        "billNumber": "lta/2025/1146",
        "billId": 108399
      },
      {
        "state": "EE",
        "billNumber": "113032019103",
        "billId": 108418
      },
      {
        "state": "EE",
        "billNumber": "749804",
        "billId": 108417
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2006-9832",
        "billId": 108273
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2021-5868",
        "billId": 108271
      },
      {
        "state": "EU",
        "billNumber": "31994L0062",
        "billId": 107262
      },
      {
        "state": "EU",
        "billNumber": "32001D0171",
        "billId": 107357
      },
      {
        "state": "EU",
        "billNumber": "32001D0753",
        "billId": 107453
      },
      {
        "state": "EU",
        "billNumber": "32009D0292",
        "billId": 107529
      },
      {
        "state": "EU",
        "billNumber": "32014L0072",
        "billId": 107365
      },
      {
        "state": "EU",
        "billNumber": "32017L2102",
        "billId": 107557
      },
      {
        "state": "EU",
        "billNumber": "32018L0849",
        "billId": 107511
      },
      {
        "state": "EU",
        "billNumber": "32020L0360",
        "billId": 107547
      },
      {
        "state": "EU",
        "billNumber": "32020L0364",
        "billId": 107549
      },
      {
        "state": "EU",
        "billNumber": "32020L0365",
        "billId": 107550
      },
      {
        "state": "EU",
        "billNumber": "32022R1616",
        "billId": 107638
      },
      {
        "state": "EU",
        "billNumber": "32023L0544",
        "billId": 107509
      },
      {
        "state": "EU",
        "billNumber": "32024L0232",
        "billId": 107559
      },
      {
        "state": "EU",
        "billNumber": "32025R0351",
        "billId": 107713
      },
      {
        "state": "FI",
        "billNumber": "2011/646",
        "billId": 108405
      },
      {
        "state": "FI",
        "billNumber": "2014/520",
        "billId": 108408
      },
      {
        "state": "FI",
        "billNumber": "2021/1029",
        "billId": 108409
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000044155771",
        "billId": 107980
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/281/made/en",
        "billId": 108325
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/283/made/en",
        "billId": 108323
      },
      {
        "state": "IN",
        "billNumber": "227250",
        "billId": 111389
      },
      {
        "state": "JP",
        "billNumber": "410CO0000000378",
        "billId": 107859
      },
      {
        "state": "JP",
        "billNumber": "413M60000400082",
        "billId": 107899
      },
      {
        "state": "JP",
        "billNumber": "413M60000400085",
        "billId": 107900
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/2017/03/21/a330/jo/fr",
        "billId": 108412
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/rgd/2018/07/02/a562/jo/fr",
        "billId": 108416
      },
      {
        "state": "NL",
        "billNumber": "BWBR0032405",
        "billId": 108246
      },
      {
        "state": "PL",
        "billNumber": "DU/2009/666",
        "billId": 108398
      },
      {
        "state": "PL",
        "billNumber": "DU/2013/888",
        "billId": 108375
      },
      {
        "state": "PL",
        "billNumber": "DU/2014/1322",
        "billId": 108397
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/150",
        "billId": 108372
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/521",
        "billId": 108392
      },
      {
        "state": "PL",
        "billNumber": "DU/2020/1114",
        "billId": 108370
      },
      {
        "state": "PL",
        "billNumber": "DU/2022/1113",
        "billId": 108388
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/160",
        "billId": 108369
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1658",
        "billId": 108368
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/1004",
        "billId": 108387
      },
      {
        "state": "SE",
        "billNumber": "sfs-1998-808",
        "billId": 108318
      },
      {
        "state": "SE",
        "billNumber": "sfs-2018-1462",
        "billId": 108294
      },
      {
        "state": "SI",
        "billNumber": "2010-01-0111",
        "billId": 108434
      },
      {
        "state": "SI",
        "billNumber": "2021-01-1053",
        "billId": 108432
      },
      {
        "state": "UK",
        "billNumber": "uksi/2003/2635",
        "billId": 108118
      },
      {
        "state": "UK",
        "billNumber": "uksi/2010/1094",
        "billId": 108171
      },
      {
        "state": "CA",
        "billNumber": "111_97_pit",
        "billId": 108589
      },
      {
        "state": "CN",
        "billNumber": "2c909fdd678bf17901678bf8bb110b8b",
        "billId": 108484
      },
      {
        "state": "CN",
        "billNumber": "ff808181927f127601936667b5d41015",
        "billId": 108465
      },
      {
        "state": "CO",
        "billNumber": "SB-25-163",
        "billId": 82272
      },
      {
        "state": "DE",
        "billNumber": "altautov",
        "billId": 108222
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2008-2387",
        "billId": 108270
      },
      {
        "state": "EU",
        "billNumber": "32000L0053",
        "billId": 107263
      },
      {
        "state": "EU",
        "billNumber": "32002D0525",
        "billId": 107504
      },
      {
        "state": "EU",
        "billNumber": "32005D0438",
        "billId": 107395
      },
      {
        "state": "EU",
        "billNumber": "32020L0361",
        "billId": 107548
      },
      {
        "state": "EU",
        "billNumber": "32020L0362",
        "billId": 107369
      },
      {
        "state": "EU",
        "billNumber": "32020L0363",
        "billId": 107370
      },
      {
        "state": "ME",
        "billNumber": "LD-474",
        "billId": 104191
      },
      {
        "state": "MN",
        "billNumber": "HF-4565",
        "billId": 1221
      },
      {
        "state": "MN",
        "billNumber": "SF-4679",
        "billId": 1222
      },
      {
        "state": "NL",
        "billNumber": "BWBR0007227",
        "billId": 108248
      },
      {
        "state": "NL",
        "billNumber": "BWBR0013707",
        "billId": 108258
      },
      {
        "state": "NL",
        "billNumber": "BWBR0016990",
        "billId": 108244
      },
      {
        "state": "UK",
        "billNumber": "nisr/1995/122",
        "billId": 108169
      },
      {
        "state": "UK",
        "billNumber": "nisr/2002/300",
        "billId": 108166
      },
      {
        "state": "UK",
        "billNumber": "uksi/1994/232",
        "billId": 108170
      },
      {
        "state": "UK",
        "billNumber": "uksi/2000/3097",
        "billId": 108168
      },
      {
        "state": "UK",
        "billNumber": "uksi/2015/63",
        "billId": 108163
      },
      {
        "state": "EU",
        "billNumber": "32006D0340",
        "billId": 107473
      },
      {
        "state": "DE",
        "billNumber": "battdg",
        "billId": 108220
      },
      {
        "state": "MN",
        "billNumber": "HF-3911",
        "billId": 104216
      },
      {
        "state": "CN",
        "billNumber": "ff80808175265dd40176b843949f3d0c",
        "billId": 108475
      },
      {
        "state": "CN",
        "billNumber": "zhengce/zhengceku/2017-01/03/content_5156043.htm",
        "billId": 108497
      },
      {
        "state": "DE",
        "billNumber": "elektrog_2015",
        "billId": 108218
      },
      {
        "state": "EU",
        "billNumber": "32024R1781",
        "billId": 107265
      },
      {
        "state": "EU",
        "billNumber": "32025R0040",
        "billId": 107258
      },
      {
        "state": "JP",
        "billNumber": "413M60000400070",
        "billId": 107886
      },
      {
        "state": "SE",
        "billNumber": "sfs-2008-834",
        "billId": 108305
      },
      {
        "state": "CO",
        "billNumber": "senado:ley_1672_2013",
        "billId": 111339
      },
      {
        "state": "JP",
        "billNumber": "413M60000400063",
        "billId": 107906
      },
      {
        "state": "JP",
        "billNumber": "413M60000400066",
        "billId": 107911
      },
      {
        "state": "NL",
        "billNumber": "BWBR0024500",
        "billId": 108250
      },
      {
        "state": "PL",
        "billNumber": "DU/2015/687",
        "billId": 108396
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047483124",
        "billId": 107806
      },
      {
        "state": "NL",
        "billNumber": "BWBR0044197",
        "billId": 108234
      },
      {
        "state": "CN",
        "billNumber": "ff8080816f3e9784016f424f1b4a04d9",
        "billId": 108443
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000041553759",
        "billId": 107838
      },
      {
        "state": "IN",
        "billNumber": "183721",
        "billId": 111386
      },
      {
        "state": "JP",
        "billNumber": "413M60000400062",
        "billId": 107908
      },
      {
        "state": "JP",
        "billNumber": "413M60000400064",
        "billId": 107912
      },
      {
        "state": "JP",
        "billNumber": "413M60000400065",
        "billId": 107909
      },
      {
        "state": "JP",
        "billNumber": "413M60000400067",
        "billId": 107905
      },
      {
        "state": "JP",
        "billNumber": "413M60000400068",
        "billId": 107910
      },
      {
        "state": "JP",
        "billNumber": "413M60000400069",
        "billId": 107907
      },
      {
        "state": "JP",
        "billNumber": "413M60000400075",
        "billId": 107883
      },
      {
        "state": "JP",
        "billNumber": "413M60000C00004",
        "billId": 107914
      },
      {
        "state": "JP",
        "billNumber": "504M60007FFE001",
        "billId": 107937
      },
      {
        "state": "LT",
        "billNumber": "TAIS.161216",
        "billId": 108429
      },
      {
        "state": "NY",
        "billNumber": "S-10168",
        "billId": 79613
      },
      {
        "state": "KY",
        "billNumber": "SB-49",
        "billId": 80507
      },
      {
        "state": "OR",
        "billNumber": "HB-4144",
        "billId": 82947
      },
      {
        "state": "WA",
        "billNumber": "SB-5144",
        "billId": 104189
      },
      {
        "state": "CT",
        "billNumber": "HB-5019",
        "billId": 81565
      },
      {
        "state": "IN",
        "billNumber": "227293",
        "billId": 111391
      },
      {
        "state": "VT",
        "billNumber": "S-254",
        "billId": 81811
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-3",
        "billId": 108104
      },
      {
        "state": "VT",
        "billNumber": "H-142",
        "billId": 72481
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2025-17186",
        "billId": 108272
      },
      {
        "state": "CH",
        "billNumber": "cc/2021/633",
        "billId": 108337
      },
      {
        "state": "CN",
        "billNumber": "zhengce/content/2017-01/03/content_5156043.htm",
        "billId": 108496
      },
      {
        "state": "JP",
        "billNumber": "413M60000400076",
        "billId": 107885
      },
      {
        "state": "JP",
        "billNumber": "425M60001400003",
        "billId": 107933
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000044036494",
        "billId": 107999
      },
      {
        "state": "OR",
        "billNumber": "HB-3780",
        "billId": 72412
      },
      {
        "state": "AU",
        "billNumber": "F2022L01222",
        "billId": 108622
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127d5c1e814c1",
        "billId": 108477
      },
      {
        "state": "DK",
        "billNumber": "lta/2014/130",
        "billId": 108401
      },
      {
        "state": "EU",
        "billNumber": "32008L0033",
        "billId": 107517
      },
      {
        "state": "EU",
        "billNumber": "32013R1257",
        "billId": 107348
      },
      {
        "state": "EU",
        "billNumber": "32017R0997",
        "billId": 107464
      },
      {
        "state": "EU",
        "billNumber": "32024R3229",
        "billId": 107746
      },
      {
        "state": "EU",
        "billNumber": "32024R3230",
        "billId": 107745
      },
      {
        "state": "FI",
        "billNumber": "2021/714",
        "billId": 108406
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000046664100",
        "billId": 107829
      },
      {
        "state": "IE",
        "billNumber": "eli/2007/si/798/made/en",
        "billId": 108326
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000110",
        "billId": 107855
      },
      {
        "state": "JP",
        "billNumber": "413M60000400079",
        "billId": 107881
      },
      {
        "state": "JP",
        "billNumber": "413M60000400080",
        "billId": 107903
      },
      {
        "state": "JP",
        "billNumber": "413M60000400092",
        "billId": 107889
      },
      {
        "state": "JP",
        "billNumber": "413M60000C00001",
        "billId": 107913
      },
      {
        "state": "JP",
        "billNumber": "508M60001400002",
        "billId": 107944
      },
      {
        "state": "JP",
        "billNumber": "508M60001440001",
        "billId": 107945
      },
      {
        "state": "PL",
        "billNumber": "DU/2013/1155",
        "billId": 108384
      },
      {
        "state": "SE",
        "billNumber": "sfs-2007-185",
        "billId": 108307
      },
      {
        "state": "SE",
        "billNumber": "sfs-2011-927",
        "billId": 108301
      },
      {
        "state": "SE",
        "billNumber": "sfs-2014-1073",
        "billId": 108299
      },
      {
        "state": "SE",
        "billNumber": "sfs-2023-132",
        "billId": 108284
      },
      {
        "state": "CN",
        "billNumber": "ff80808175265dd40175f97b3fbc2377",
        "billId": 108447
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-1000",
        "billId": 108291
      },
      {
        "state": "CA",
        "billNumber": "AB-732",
        "billId": 80259
      },
      {
        "state": "PL",
        "billNumber": "DU/2015/1688",
        "billId": 108383
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/1895",
        "billId": 108380
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000031056680",
        "billId": 107994
      },
      {
        "state": "ME",
        "billNumber": "LD-1541",
        "billId": 79534
      },
      {
        "state": "BR",
        "billNumber": "_ato2007-2010/2010/lei/l12305.htm",
        "billId": 108332
      },
      {
        "state": "CN",
        "billNumber": "zhengce/zhengceku/2008-03/28/content_2047.htm",
        "billId": 108499
      },
      {
        "state": "NL",
        "billNumber": "BWBR0048299",
        "billId": 108235
      },
      {
        "state": "CL",
        "billNumber": "1090894",
        "billId": 108275
      },
      {
        "state": "CN",
        "billNumber": "ff8081818b6b80c1018b6f0b15700b8e",
        "billId": 108468
      },
      {
        "state": "CN",
        "billNumber": "zhengce/zhengceku/2021-02/22/content_5588274.htm",
        "billId": 108498
      },
      {
        "state": "CZ",
        "billNumber": "2020/541",
        "billId": 108438
      },
      {
        "state": "DE",
        "billNumber": "krwg",
        "billId": 108221
      },
      {
        "state": "EU",
        "billNumber": "32001D0524",
        "billId": 107336
      },
      {
        "state": "EU",
        "billNumber": "32012R1179",
        "billId": 107491
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10",
        "billId": 108100
      },
      {
        "state": "JP",
        "billNumber": "414M60001400007",
        "billId": 107923
      },
      {
        "state": "JP",
        "billNumber": "504M60001400001",
        "billId": 107940
      },
      {
        "state": "LV",
        "billNumber": "221378",
        "billId": 108420
      },
      {
        "state": "OR",
        "billNumber": "SB-1520",
        "billId": 83268
      },
      {
        "state": "PL",
        "billNumber": "DU/2017/2056",
        "billId": 108373
      },
      {
        "state": "SE",
        "billNumber": "sfs-2001-1063",
        "billId": 108312
      },
      {
        "state": "BR",
        "billNumber": "_ato2023-2026/2023/decreto/D11413.htm",
        "billId": 108334
      },
      {
        "state": "UK",
        "billNumber": "nisr/2006/519",
        "billId": 108153
      },
      {
        "state": "DK",
        "billNumber": "lta/2019/1337",
        "billId": 108403
      },
      {
        "state": "EU",
        "billNumber": "32004L0012",
        "billId": 107378
      },
      {
        "state": "EU",
        "billNumber": "32025R2269",
        "billId": 107759
      },
      {
        "state": "LT",
        "billNumber": "TAIS.59267",
        "billId": 108428
      },
      {
        "state": "SK",
        "billNumber": "2015/373",
        "billId": 108425
      },
      {
        "state": "CA",
        "billNumber": "200_2007",
        "billId": 108585
      },
      {
        "state": "CN",
        "billNumber": "ff808181799def980179ad26f28814aa",
        "billId": 108463
      },
      {
        "state": "EU",
        "billNumber": "32004D0249",
        "billId": 107401
      },
      {
        "state": "EU",
        "billNumber": "32014D0955",
        "billId": 107497
      },
      {
        "state": "EU",
        "billNumber": "32019D2193",
        "billId": 107624
      },
      {
        "state": "EU",
        "billNumber": "32025R1561",
        "billId": 107689
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000052450618",
        "billId": 107972
      },
      {
        "state": "JP",
        "billNumber": "413M60001400001",
        "billId": 107915
      },
      {
        "state": "JP",
        "billNumber": "413M60001500001",
        "billId": 107877
      },
      {
        "state": "JP",
        "billNumber": "508M60001400003",
        "billId": 107943
      },
      {
        "state": "LT",
        "billNumber": "TAIS.325345",
        "billId": 108431
      },
      {
        "state": "PE",
        "billNumber": "ds-009-2019-minam",
        "billId": 111348
      },
      {
        "state": "PL",
        "billNumber": "DU/2017/2422",
        "billId": 108363
      },
      {
        "state": "SI",
        "billNumber": "2015-01-1513",
        "billId": 108433
      },
      {
        "state": "LV",
        "billNumber": "267716",
        "billId": 108423
      },
      {
        "state": "CN",
        "billNumber": "zhengce/zhengceku/2010-12/31/content_5041.htm",
        "billId": 108502
      },
      {
        "state": "EU",
        "billNumber": "32009D0851",
        "billId": 107486
      },
      {
        "state": "EU",
        "billNumber": "32019D0638",
        "billId": 107572
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-26",
        "billId": 108112
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/149/made/en",
        "billId": 108322
      },
      {
        "state": "JP",
        "billNumber": "414CO0000000389",
        "billId": 107862
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/1994/06/17/n4/jo/fr",
        "billId": 108415
      },
      {
        "state": "EU",
        "billNumber": "32025R0606",
        "billId": 107758
      },
      {
        "state": "CN",
        "billNumber": "ff8081818364d903018407f6c4887544",
        "billId": 108461
      },
      {
        "state": "CN",
        "billNumber": "ff8081818a1cb709018a24ff766d20df",
        "billId": 108469
      },
      {
        "state": "CN",
        "billNumber": "ff808181927f12760194167453206544",
        "billId": 108467
      },
      {
        "state": "EU",
        "billNumber": "32001D0118",
        "billId": 107540
      },
      {
        "state": "EU",
        "billNumber": "32001D0573",
        "billId": 107289
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000029387124",
        "billId": 108010
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1587",
        "billId": 108344
      },
      {
        "state": "CA",
        "billNumber": "AB-707",
        "billId": 80248
      },
      {
        "state": "LV",
        "billNumber": "124707",
        "billId": 108422
      },
      {
        "state": "SE",
        "billNumber": "sfs-2007-193",
        "billId": 108306
      },
      {
        "state": "UK",
        "billNumber": "uksi/2015/1935",
        "billId": 108159
      },
      {
        "state": "DK",
        "billNumber": "lta/2015/1453",
        "billId": 108402
      },
      {
        "state": "EU",
        "billNumber": "32016D2323",
        "billId": 107279
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043327059",
        "billId": 107977
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/992",
        "billId": 108361
      },
      {
        "state": "JP",
        "billNumber": "425M60001000005",
        "billId": 107932
      },
      {
        "state": "UK",
        "billNumber": "uksi/2001/2551",
        "billId": 108167
      },
      {
        "state": "CN",
        "billNumber": "ff8081817fd9834101804ef8f5bf71f5",
        "billId": 108473
      },
      {
        "state": "EU",
        "billNumber": "32008L0098",
        "billId": 107264
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/21",
        "billId": 108362
      },
      {
        "state": "UK",
        "billNumber": "ssi/2009/247",
        "billId": 108160
      },
      {
        "state": "DC",
        "billNumber": "D.C. Law 24-320",
        "billId": 104190
      },
      {
        "state": "MD",
        "billNumber": "SB-686",
        "billId": 72278
      },
      {
        "state": "BR",
        "billNumber": "_ato2019-2022/2022/decreto/D10936.htm",
        "billId": 108333
      },
      {
        "state": "UK",
        "billNumber": "uksi/2018/1214",
        "billId": 108146
      },
      {
        "state": "PE",
        "billNumber": "dl-1278",
        "billId": 111346
      },
      {
        "state": "SE",
        "billNumber": "sfs-1998-902",
        "billId": 108315
      },
      {
        "state": "UK",
        "billNumber": "nisr/2009/159",
        "billId": 108161
      },
      {
        "state": "OR",
        "billNumber": "HB-3220",
        "billId": 80376
      },
      {
        "state": "NY",
        "billNumber": "A-10284",
        "billId": 80208
      },
      {
        "state": "SE",
        "billNumber": "sfs-2025-813",
        "billId": 108285
      }
    ]
  },
  {
    "lever": "material_restriction",
    "name": "Material Restrictions",
    "headline": "Avoid banned / restricted materials and formats",
    "direction": "Eliminate microplastic particles from cosmetic product formulations.",
    "focus": [
      "Packaging",
      "Organics",
      "Electronics",
      "Textiles",
      "Hazardous materials",
      "Construction",
      "Biobased"
    ],
    "billCount": 132,
    "states": [
      "AT",
      "AU",
      "BR",
      "CA",
      "CH",
      "CL",
      "CN",
      "CO",
      "DE",
      "DK",
      "EE",
      "ES",
      "EU",
      "FI",
      "FR",
      "IE",
      "IN",
      "JP",
      "LU",
      "LV",
      "ME",
      "MX",
      "NL",
      "NY",
      "PE",
      "PL",
      "RI",
      "SC",
      "SE",
      "SI",
      "SK",
      "UK",
      "VT",
      "WA"
    ],
    "evidence": {
      "state": "BR",
      "bill": "2203624",
      "quote": "Prohibition on using microplastic particles in the composition of cosmetic products"
    },
    "examples": [
      {
        "action": "Eliminate microplastic particles from cosmetic product formulations.",
        "state": "BR",
        "billNumber": "2203624",
        "billId": 111383,
        "quote": "Prohibition on using microplastic particles in the composition of cosmetic products"
      },
      {
        "action": "Eliminate single-use plastic carryout bags by January 1, 2024.",
        "state": "CO",
        "billNumber": "HB-21-1162",
        "billId": 72433,
        "quote": "On and after January 1, 2024: Do NOT provide single-use plastic carryout bags to customers (with limited inventory exception through June 1, 2024)"
      },
      {
        "action": "Do not use plastic for cotton buds, cutlery, plates, straws, stirrers, balloon sticks.",
        "state": "DE",
        "billNumber": "ewkverbotsv",
        "billId": 108224,
        "quote": "Single-use plastic cotton buds (Wattestäbchen) made wholly or partly of plastic"
      }
    ],
    "feeImpact": {
      "malus": true,
      "bonus": false,
      "setJurisdictions": [
        "CH",
        "EE",
        "EU",
        "FR",
        "LV",
        "NL",
        "PL",
        "SI",
        "UK"
      ],
      "usPending": true,
      "examples": [
        {
          "jurisdiction": "CH",
          "amount": "0.3 CHF deposit minimum"
        },
        {
          "jurisdiction": "EE",
          "amount": "40.0 EEK/kg"
        }
      ]
    },
    "bills": [
      {
        "state": "BR",
        "billNumber": "2203624",
        "billId": 111383
      },
      {
        "state": "CO",
        "billNumber": "HB-21-1162",
        "billId": 72433
      },
      {
        "state": "DE",
        "billNumber": "ewkverbotsv",
        "billId": 108224
      },
      {
        "state": "PE",
        "billNumber": "ley-30884",
        "billId": 111349
      },
      {
        "state": "UK",
        "billNumber": "ssi/2021/410",
        "billId": 108176
      },
      {
        "state": "CA",
        "billNumber": "406_97_pit",
        "billId": 108587
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016128016d2f42e7",
        "billId": 108445
      },
      {
        "state": "IE",
        "billNumber": "eli/2024/si/33/made/en",
        "billId": 108321
      },
      {
        "state": "UK",
        "billNumber": "ssi/2025/188",
        "billId": 108178
      },
      {
        "state": "IN",
        "billNumber": "227249",
        "billId": 111387
      },
      {
        "state": "AT",
        "billNumber": "20002086",
        "billId": 108327
      },
      {
        "state": "AU",
        "billNumber": "act-2021-031",
        "billId": 108643
      },
      {
        "state": "CN",
        "billNumber": "ff8081818364d903018407f6c4887544",
        "billId": 108461
      },
      {
        "state": "CN",
        "billNumber": "ff808181927f127601936667b5d41015",
        "billId": 108465
      },
      {
        "state": "EE",
        "billNumber": "113032019103",
        "billId": 108418
      },
      {
        "state": "EU",
        "billNumber": "32008D0440",
        "billId": 107287
      },
      {
        "state": "EU",
        "billNumber": "32015L0720",
        "billId": 107334
      },
      {
        "state": "EU",
        "billNumber": "32022D0162",
        "billId": 107613
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000053625694",
        "billId": 107832
      },
      {
        "state": "IN",
        "billNumber": "183721",
        "billId": 111386
      },
      {
        "state": "JP",
        "billNumber": "418M60000740001",
        "billId": 107928
      },
      {
        "state": "JP",
        "billNumber": "420M60000600001",
        "billId": 107931
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/2017/03/21/a330/jo/fr",
        "billId": 108412
      },
      {
        "state": "LV",
        "billNumber": "57207",
        "billId": 108421
      },
      {
        "state": "ME",
        "billNumber": "LD-754",
        "billId": 72241
      },
      {
        "state": "NL",
        "billNumber": "BWBR0037392",
        "billId": 108241
      },
      {
        "state": "NY",
        "billNumber": "A-7912",
        "billId": 83358
      },
      {
        "state": "PL",
        "billNumber": "DU/2017/2056",
        "billId": 108373
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-1000",
        "billId": 108291
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-1002",
        "billId": 108289
      },
      {
        "state": "SI",
        "billNumber": "2021-01-2724",
        "billId": 108436
      },
      {
        "state": "UK",
        "billNumber": "wsi/2023/1149",
        "billId": 108175
      },
      {
        "state": "UK",
        "billNumber": "wsi/2023/1288",
        "billId": 108174
      },
      {
        "state": "UK",
        "billNumber": "wsi/2025/716",
        "billId": 108173
      },
      {
        "state": "WA",
        "billNumber": "SB-5284",
        "billId": 104217
      },
      {
        "state": "DE",
        "billNumber": "ewkfondsg",
        "billId": 108223
      },
      {
        "state": "ME",
        "billNumber": "LD-1467",
        "billId": 72366
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-999",
        "billId": 108286
      },
      {
        "state": "AT",
        "billNumber": "20008902",
        "billId": 108328
      },
      {
        "state": "EU",
        "billNumber": "32021R1929",
        "billId": 107621
      },
      {
        "state": "EU",
        "billNumber": "32023D1060",
        "billId": 107719
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000042753962",
        "billId": 107830
      },
      {
        "state": "SE",
        "billNumber": "sfs-2018-1462",
        "billId": 108294
      },
      {
        "state": "UK",
        "billNumber": "ssi/2020/154",
        "billId": 108182
      },
      {
        "state": "UK",
        "billNumber": "ssi/2025/189",
        "billId": 108177
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2022-5809",
        "billId": 108267
      },
      {
        "state": "EU",
        "billNumber": "32025R0351",
        "billId": 107713
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1658",
        "billId": 108368
      },
      {
        "state": "CA",
        "billNumber": "SB-279",
        "billId": 103008
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000046285336",
        "billId": 107959
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/542",
        "billId": 108371
      },
      {
        "state": "UK",
        "billNumber": "uksi/2020/904",
        "billId": 108143
      },
      {
        "state": "SE",
        "billNumber": "sfs-2005-220",
        "billId": 108310
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-3",
        "billId": 108104
      },
      {
        "state": "NL",
        "billNumber": "BWBR0051106",
        "billId": 108262
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127c954530a34",
        "billId": 108446
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127e112bb1ff4",
        "billId": 108449
      },
      {
        "state": "CN",
        "billNumber": "ff808081752b7d430176b1a842ea3f28",
        "billId": 108476
      },
      {
        "state": "CN",
        "billNumber": "ff8081817fc0f0f0017fd4fae0a7133e",
        "billId": 108450
      },
      {
        "state": "CN",
        "billNumber": "ff808181927f0931019325530cb6751c",
        "billId": 108464
      },
      {
        "state": "JP",
        "billNumber": "504CO0000000025",
        "billId": 107865
      },
      {
        "state": "LV",
        "billNumber": "124707",
        "billId": 108422
      },
      {
        "state": "NL",
        "billNumber": "BWBR0046477",
        "billId": 108260
      },
      {
        "state": "CO",
        "billNumber": "HB-22-1355",
        "billId": 72416
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000025423069",
        "billId": 108042
      },
      {
        "state": "JP",
        "billNumber": "410CO0000000378",
        "billId": 107859
      },
      {
        "state": "JP",
        "billNumber": "413M60000740001",
        "billId": 107916
      },
      {
        "state": "JP",
        "billNumber": "413M60001500001",
        "billId": 107877
      },
      {
        "state": "CA",
        "billNumber": "regulation/210391",
        "billId": 108593
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043799891",
        "billId": 107990
      },
      {
        "state": "CH",
        "billNumber": "cc/2000/299",
        "billId": 108340
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000041553759",
        "billId": 107838
      },
      {
        "state": "SI",
        "billNumber": "2021-01-1053",
        "billId": 108432
      },
      {
        "state": "CA",
        "billNumber": "111_97_pit",
        "billId": 108589
      },
      {
        "state": "CN",
        "billNumber": "ff80808175265dd40176b843949f3d0c",
        "billId": 108475
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/150",
        "billId": 108372
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2024-21709",
        "billId": 108274
      },
      {
        "state": "EU",
        "billNumber": "32004L0012",
        "billId": 107378
      },
      {
        "state": "JP",
        "billNumber": "413M60000740002",
        "billId": 107917
      },
      {
        "state": "SE",
        "billNumber": "sfs-2007-185",
        "billId": 108307
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043458675",
        "billId": 107815
      },
      {
        "state": "EE",
        "billNumber": "918053",
        "billId": 108419
      },
      {
        "state": "PL",
        "billNumber": "DU/2020/1114",
        "billId": 108370
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/927",
        "billId": 108366
      },
      {
        "state": "EU",
        "billNumber": "32025R0040",
        "billId": 107258
      },
      {
        "state": "CN",
        "billNumber": "ff8080816f135f46016f1d06082912c2",
        "billId": 108441
      },
      {
        "state": "DK",
        "billNumber": "lta/2025/882",
        "billId": 108400
      },
      {
        "state": "EU",
        "billNumber": "32001D0573",
        "billId": 107289
      },
      {
        "state": "EU",
        "billNumber": "32023D2106",
        "billId": 107710
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032610837",
        "billId": 107843
      },
      {
        "state": "JP",
        "billNumber": "504M60001000001",
        "billId": 107939
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1587",
        "billId": 108344
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/160",
        "billId": 108369
      },
      {
        "state": "SK",
        "billNumber": "2019/302",
        "billId": 108427
      },
      {
        "state": "CL",
        "billNumber": "1208163",
        "billId": 108279
      },
      {
        "state": "EU",
        "billNumber": "32020R0762",
        "billId": 107585
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/1911",
        "billId": 108365
      },
      {
        "state": "CA",
        "billNumber": "SB-303",
        "billId": 733
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127d5c1e814c1",
        "billId": 108477
      },
      {
        "state": "CN",
        "billNumber": "ff80808175265dd40175f97b3fbc2377",
        "billId": 108447
      },
      {
        "state": "PL",
        "billNumber": "DU/2016/1863",
        "billId": 108374
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032187830",
        "billId": 108011
      },
      {
        "state": "MX",
        "billNumber": "LGPGIR",
        "billId": 111332
      },
      {
        "state": "UK",
        "billNumber": "nisr/2020/285",
        "billId": 108144
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000049184670",
        "billId": 107816
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-1",
        "billId": 108096
      },
      {
        "state": "UK",
        "billNumber": "ssi/2025/10",
        "billId": 108142
      },
      {
        "state": "JP",
        "billNumber": "504M60001400001",
        "billId": 107940
      },
      {
        "state": "SC",
        "billNumber": "S-171",
        "billId": 104219
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-1001",
        "billId": 108290
      },
      {
        "state": "CN",
        "billNumber": "ff808181927f12760194167453206544",
        "billId": 108467
      },
      {
        "state": "CO",
        "billNumber": "HB22-1355",
        "billId": 104215
      },
      {
        "state": "VT",
        "billNumber": "H-915",
        "billId": 1213
      },
      {
        "state": "FI",
        "billNumber": "2021/1029",
        "billId": 108409
      },
      {
        "state": "VT",
        "billNumber": "H-142",
        "billId": 72481
      },
      {
        "state": "EU",
        "billNumber": "32021D1752",
        "billId": 107618
      },
      {
        "state": "JP",
        "billNumber": "507CO0000000003",
        "billId": 107866
      },
      {
        "state": "CN",
        "billNumber": "zhengce/zhengceku/2021-02/22/content_5588274.htm",
        "billId": 108498
      },
      {
        "state": "UK",
        "billNumber": "wsi/2011/551",
        "billId": 108196
      },
      {
        "state": "JP",
        "billNumber": "508M60000740004",
        "billId": 107957
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/21",
        "billId": 108362
      },
      {
        "state": "PL",
        "billNumber": "DU/2020/797",
        "billId": 108354
      },
      {
        "state": "EU",
        "billNumber": "32005D0270",
        "billId": 107391
      },
      {
        "state": "SE",
        "billNumber": "sfs-2016-1041",
        "billId": 108296
      },
      {
        "state": "SE",
        "billNumber": "sfs-1998-902",
        "billId": 108315
      },
      {
        "state": "CN",
        "billNumber": "ff8081818a1cb709018a24ff766d20df",
        "billId": 108469
      },
      {
        "state": "AU",
        "billNumber": "act-2011-031",
        "billId": 108640
      },
      {
        "state": "JP",
        "billNumber": "407CO0000000411",
        "billId": 107858
      },
      {
        "state": "EU",
        "billNumber": "32021D1384",
        "billId": 107619
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047274648",
        "billId": 107848
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/1403",
        "billId": 108356
      },
      {
        "state": "RI",
        "billNumber": "SB-996",
        "billId": 79521
      }
    ]
  },
  {
    "lever": "labeling_marking",
    "name": "Labeling & Marking",
    "headline": "Apply required recyclability / disposal labeling",
    "direction": "Add chemical symbols (Hg, Cd, Pb) below bin symbol if mercury >0.0005%, cadmium >0.002%, or lead >0.004%.",
    "focus": [
      "Packaging",
      "Electronics",
      "Batteries",
      "Hazardous materials",
      "Organics",
      "Textiles",
      "Vehicles"
    ],
    "billCount": 277,
    "states": [
      "AT",
      "AU",
      "BR",
      "CA",
      "CH",
      "CL",
      "CN",
      "CO",
      "CT",
      "DE",
      "DK",
      "EE",
      "ES",
      "EU",
      "FI",
      "FR",
      "IE",
      "IL",
      "IN",
      "JP",
      "KY",
      "LT",
      "LU",
      "LV",
      "MD",
      "ME",
      "MI",
      "MN",
      "MX",
      "NL",
      "NY",
      "OR",
      "PE",
      "PL",
      "RI",
      "SE",
      "SI",
      "SK",
      "UK",
      "UY",
      "VT"
    ],
    "evidence": {
      "state": "NL",
      "bill": "BWBR0024492",
      "quote": "Batteries/accumulators containing >0.0005 wt% mercury, >0.002 wt% cadmium, or >0.004 wt% lead must bear the relevant chemical symbol (Hg, Cd, or Pb) below the crossed-out bin symbol, occupying at least one quarter of the symbol's dimensions (Articles 9(4)-(6))."
    },
    "examples": [
      {
        "action": "Add chemical symbols (Hg, Cd, Pb) below bin symbol if mercury >0.0005%, cadmium >0.002%, or lead >0.004%.",
        "state": "NL",
        "billNumber": "BWBR0024492",
        "billId": 108251,
        "quote": "Batteries/accumulators containing >0.0005 wt% mercury, >0.002 wt% cadmium, or >0.004 wt% lead must bear the relevant chemical symbol (Hg, Cd, or Pb) below the crossed-out bin symbol, occupying at least one quarter of the symbol's dimensions (Articles 9(4)-(6))."
      },
      {
        "action": "Label all batteries with crossed-out wheeled bin symbol and chemical symbols (Hg, Cd, Pb) where applicable.",
        "state": "FI",
        "billNumber": "2014/520",
        "billId": 108408,
        "quote": "Label all batteries, accumulators, and battery packs placed on the market with the crossed-out wheeled bin symbol and chemical symbols (Hg, Cd, Pb) where applicable (per Annex 2)"
      },
      {
        "action": "Label recycled packaging with percentage recycled content per IS 14534:2023.",
        "state": "IN",
        "billNumber": "227249",
        "billId": 111387,
        "quote": "Recycled plastic packaging must bear label specifying percentage of recycled plastic and conform to IS 14534:2023"
      }
    ],
    "feeImpact": {
      "malus": true,
      "bonus": true,
      "setJurisdictions": [
        "AU",
        "CN",
        "DK",
        "FR"
      ],
      "usPending": true,
      "examples": []
    },
    "bills": [
      {
        "state": "NL",
        "billNumber": "BWBR0024492",
        "billId": 108251
      },
      {
        "state": "FI",
        "billNumber": "2014/520",
        "billId": 108408
      },
      {
        "state": "IN",
        "billNumber": "227249",
        "billId": 111387
      },
      {
        "state": "JP",
        "billNumber": "413M60000400080",
        "billId": 107903
      },
      {
        "state": "JP",
        "billNumber": "413M60000400085",
        "billId": 107900
      },
      {
        "state": "JP",
        "billNumber": "413M60000400086",
        "billId": 107902
      },
      {
        "state": "NL",
        "billNumber": "BWBR0037392",
        "billId": 108241
      },
      {
        "state": "NY",
        "billNumber": "A-7912",
        "billId": 83358
      },
      {
        "state": "UK",
        "billNumber": "nisr/1995/122",
        "billId": 108169
      },
      {
        "state": "UK",
        "billNumber": "uksi/1994/232",
        "billId": 108170
      },
      {
        "state": "CA",
        "billNumber": "406_97_pit",
        "billId": 108587
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016128016d2f42e7",
        "billId": 108445
      },
      {
        "state": "EU",
        "billNumber": "32006L0066",
        "billId": 107349
      },
      {
        "state": "JP",
        "billNumber": "413M60000400076",
        "billId": 107885
      },
      {
        "state": "JP",
        "billNumber": "413M60000400088",
        "billId": 107901
      },
      {
        "state": "JP",
        "billNumber": "413M60000400090",
        "billId": 107890
      },
      {
        "state": "JP",
        "billNumber": "413M60000400091",
        "billId": 107888
      },
      {
        "state": "JP",
        "billNumber": "413M60000C00001",
        "billId": 107913
      },
      {
        "state": "PL",
        "billNumber": "DU/2015/687",
        "billId": 108396
      },
      {
        "state": "AT",
        "billNumber": "20005815",
        "billId": 108330
      },
      {
        "state": "AU",
        "billNumber": "act-2001-058",
        "billId": 108642
      },
      {
        "state": "AU",
        "billNumber": "act-2022-005",
        "billId": 108641
      },
      {
        "state": "CA",
        "billNumber": "SB-1215",
        "billId": 797
      },
      {
        "state": "CA",
        "billNumber": "SB-343",
        "billId": 81917
      },
      {
        "state": "CA",
        "billNumber": "SB-814",
        "billId": 742
      },
      {
        "state": "CH",
        "billNumber": "cc/2000/299",
        "billId": 108340
      },
      {
        "state": "CH",
        "billNumber": "cc/2021/633",
        "billId": 108337
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127e112bb1ff4",
        "billId": 108449
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127fab8a83b90",
        "billId": 108471
      },
      {
        "state": "CT",
        "billNumber": "HB-5019",
        "billId": 81565
      },
      {
        "state": "DE",
        "billNumber": "battg",
        "billId": 108219
      },
      {
        "state": "DK",
        "billNumber": "lta/2019/1218",
        "billId": 108404
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2015-1762",
        "billId": 108269
      },
      {
        "state": "EU",
        "billNumber": "32003D0138",
        "billId": 107466
      },
      {
        "state": "EU",
        "billNumber": "32009R0641",
        "billId": 107299
      },
      {
        "state": "EU",
        "billNumber": "32009R0767",
        "billId": 107456
      },
      {
        "state": "EU",
        "billNumber": "32010R1103",
        "billId": 107419
      },
      {
        "state": "EU",
        "billNumber": "32012L0019",
        "billId": 107259
      },
      {
        "state": "EU",
        "billNumber": "32020R0762",
        "billId": 107585
      },
      {
        "state": "EU",
        "billNumber": "32020R2151",
        "billId": 107601
      },
      {
        "state": "EU",
        "billNumber": "32024L0232",
        "billId": 107559
      },
      {
        "state": "EU",
        "billNumber": "32024L0884",
        "billId": 107561
      },
      {
        "state": "EU",
        "billNumber": "32025R2269",
        "billId": 107759
      },
      {
        "state": "FI",
        "billNumber": "2011/646",
        "billId": 108405
      },
      {
        "state": "FI",
        "billNumber": "2014/519",
        "billId": 108407
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000029958108",
        "billId": 108041
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000041553759",
        "billId": 107838
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043714227",
        "billId": 107847
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000046005259",
        "billId": 107846
      },
      {
        "state": "IE",
        "billNumber": "eli/2024/si/33/made/en",
        "billId": 108321
      },
      {
        "state": "IN",
        "billNumber": "183711",
        "billId": 111388
      },
      {
        "state": "IN",
        "billNumber": "183721",
        "billId": 111386
      },
      {
        "state": "JP",
        "billNumber": "405M50000400034",
        "billId": 107870
      },
      {
        "state": "JP",
        "billNumber": "405M50000500001",
        "billId": 107869
      },
      {
        "state": "JP",
        "billNumber": "410AC0000000097",
        "billId": 107691
      },
      {
        "state": "JP",
        "billNumber": "412M50000500001",
        "billId": 107876
      },
      {
        "state": "JP",
        "billNumber": "413M60000400079",
        "billId": 107881
      },
      {
        "state": "JP",
        "billNumber": "413M60000400082",
        "billId": 107899
      },
      {
        "state": "JP",
        "billNumber": "413M60000400087",
        "billId": 107896
      },
      {
        "state": "JP",
        "billNumber": "413M60000400089",
        "billId": 107898
      },
      {
        "state": "JP",
        "billNumber": "413M60000400092",
        "billId": 107889
      },
      {
        "state": "JP",
        "billNumber": "413M60000740001",
        "billId": 107916
      },
      {
        "state": "JP",
        "billNumber": "413M60000740002",
        "billId": 107917
      },
      {
        "state": "JP",
        "billNumber": "413M60001F40004",
        "billId": 107921
      },
      {
        "state": "JP",
        "billNumber": "414M60001400007",
        "billId": 107923
      },
      {
        "state": "KY",
        "billNumber": "SB-49",
        "billId": 80507
      },
      {
        "state": "LT",
        "billNumber": "TAIS.161216",
        "billId": 108429
      },
      {
        "state": "LV",
        "billNumber": "267716",
        "billId": 108423
      },
      {
        "state": "ME",
        "billNumber": "LD-1564",
        "billId": 83401
      },
      {
        "state": "ME",
        "billNumber": "LD-1909",
        "billId": 83470
      },
      {
        "state": "MI",
        "billNumber": "SB-416",
        "billId": 73159
      },
      {
        "state": "NL",
        "billNumber": "BWBR0004785",
        "billId": 108240
      },
      {
        "state": "NL",
        "billNumber": "BWBR0006253",
        "billId": 108252
      },
      {
        "state": "NL",
        "billNumber": "BWBR0017053",
        "billId": 108247
      },
      {
        "state": "NL",
        "billNumber": "BWBR0034782",
        "billId": 108245
      },
      {
        "state": "OR",
        "billNumber": "SB-1520",
        "billId": 83268
      },
      {
        "state": "PL",
        "billNumber": "DU/2005/1495",
        "billId": 108386
      },
      {
        "state": "PL",
        "billNumber": "DU/2008/1464",
        "billId": 108385
      },
      {
        "state": "PL",
        "billNumber": "DU/2009/666",
        "billId": 108398
      },
      {
        "state": "PL",
        "billNumber": "DU/2013/1155",
        "billId": 108384
      },
      {
        "state": "PL",
        "billNumber": "DU/2015/1688",
        "billId": 108383
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/1466",
        "billId": 108381
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/1895",
        "billId": 108380
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/521",
        "billId": 108392
      },
      {
        "state": "PL",
        "billNumber": "DU/2020/1893",
        "billId": 108379
      },
      {
        "state": "PL",
        "billNumber": "DU/2022/1113",
        "billId": 108388
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1852",
        "billId": 108367
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/1004",
        "billId": 108387
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/1911",
        "billId": 108365
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/573",
        "billId": 108376
      },
      {
        "state": "SE",
        "billNumber": "sfs-2005-209",
        "billId": 108311
      },
      {
        "state": "SE",
        "billNumber": "sfs-2005-220",
        "billId": 108310
      },
      {
        "state": "SE",
        "billNumber": "sfs-2007-193",
        "billId": 108306
      },
      {
        "state": "SE",
        "billNumber": "sfs-2008-834",
        "billId": 108305
      },
      {
        "state": "SE",
        "billNumber": "sfs-2018-1462",
        "billId": 108294
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-1000",
        "billId": 108291
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-998",
        "billId": 108287
      },
      {
        "state": "SI",
        "billNumber": "2021-01-2724",
        "billId": 108436
      },
      {
        "state": "SI",
        "billNumber": "2024-01-2498",
        "billId": 108435
      },
      {
        "state": "SK",
        "billNumber": "2015/373",
        "billId": 108425
      },
      {
        "state": "SK",
        "billNumber": "2019/302",
        "billId": 108427
      },
      {
        "state": "UK",
        "billNumber": "ssi/2020/154",
        "billId": 108182
      },
      {
        "state": "UK",
        "billNumber": "ssi/2023/201",
        "billId": 108180
      },
      {
        "state": "UK",
        "billNumber": "ssi/2025/188",
        "billId": 108178
      },
      {
        "state": "UK",
        "billNumber": "ssi/2025/189",
        "billId": 108177
      },
      {
        "state": "UK",
        "billNumber": "uksi/2001/2551",
        "billId": 108167
      },
      {
        "state": "UK",
        "billNumber": "uksi/2012/1139",
        "billId": 108164
      },
      {
        "state": "UK",
        "billNumber": "uksi/2014/1771",
        "billId": 108149
      },
      {
        "state": "VT",
        "billNumber": "H-175",
        "billId": 72450
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-3",
        "billId": 108104
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032847905",
        "billId": 107814
      },
      {
        "state": "CO",
        "billNumber": "senado:ley_1672_2013",
        "billId": 111339
      },
      {
        "state": "DE",
        "billNumber": "elektrog_2015",
        "billId": 108218
      },
      {
        "state": "JP",
        "billNumber": "413M60000400083",
        "billId": 107897
      },
      {
        "state": "LV",
        "billNumber": "57207",
        "billId": 108421
      },
      {
        "state": "CN",
        "billNumber": "2c909fdd678bf17901678bf737800631",
        "billId": 108442
      },
      {
        "state": "DK",
        "billNumber": "lta/2015/1453",
        "billId": 108402
      },
      {
        "state": "EU",
        "billNumber": "32009D0292",
        "billId": 107529
      },
      {
        "state": "FI",
        "billNumber": "2021/714",
        "billId": 108406
      },
      {
        "state": "NL",
        "billNumber": "BWBR0007227",
        "billId": 108248
      },
      {
        "state": "NL",
        "billNumber": "BWBR0013707",
        "billId": 108258
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-18",
        "billId": 108106
      },
      {
        "state": "BR",
        "billNumber": "2565302",
        "billId": 111365
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127c954530a34",
        "billId": 108446
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2024-21709",
        "billId": 108274
      },
      {
        "state": "EU",
        "billNumber": "32024R1781",
        "billId": 107265
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000029881868",
        "billId": 108048
      },
      {
        "state": "JP",
        "billNumber": "403AC0000000048",
        "billId": 107692
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000110",
        "billId": 107855
      },
      {
        "state": "JP",
        "billNumber": "508M60001400002",
        "billId": 107944
      },
      {
        "state": "JP",
        "billNumber": "508M60001440001",
        "billId": 107945
      },
      {
        "state": "MN",
        "billNumber": "SF-4679",
        "billId": 1222
      },
      {
        "state": "SE",
        "billNumber": "sfs-2009-1031",
        "billId": 108303
      },
      {
        "state": "SI",
        "billNumber": "2021-01-1053",
        "billId": 108432
      },
      {
        "state": "CA",
        "billNumber": "SB-1013",
        "billId": 851
      },
      {
        "state": "CN",
        "billNumber": "zhengce/zhengceku/2017-01/03/content_5156043.htm",
        "billId": 108497
      },
      {
        "state": "AT",
        "billNumber": "20002086",
        "billId": 108327
      },
      {
        "state": "CN",
        "billNumber": "ff8080816f135f46016f1d06082912c2",
        "billId": 108441
      },
      {
        "state": "CN",
        "billNumber": "ff8081817fc0f0f0017fd4fae0a7133e",
        "billId": 108450
      },
      {
        "state": "CN",
        "billNumber": "zhengce/content/2017-01/03/content_5156043.htm",
        "billId": 108496
      },
      {
        "state": "DE",
        "billNumber": "altautov",
        "billId": 108222
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2021-5868",
        "billId": 108271
      },
      {
        "state": "EU",
        "billNumber": "32021R1929",
        "billId": 107621
      },
      {
        "state": "EU",
        "billNumber": "32023L0544",
        "billId": 107509
      },
      {
        "state": "EU",
        "billNumber": "32025R0040",
        "billId": 107258
      },
      {
        "state": "FI",
        "billNumber": "2021/1029",
        "billId": 108409
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000026863961",
        "billId": 108044
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032770063",
        "billId": 108043
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000046664100",
        "billId": 107829
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10",
        "billId": 108100
      },
      {
        "state": "JP",
        "billNumber": "410CO0000000378",
        "billId": 107859
      },
      {
        "state": "JP",
        "billNumber": "413M60000400062",
        "billId": 107908
      },
      {
        "state": "JP",
        "billNumber": "413M60000400070",
        "billId": 107886
      },
      {
        "state": "JP",
        "billNumber": "413M60000400071",
        "billId": 107878
      },
      {
        "state": "JP",
        "billNumber": "413M60000400072",
        "billId": 107882
      },
      {
        "state": "JP",
        "billNumber": "413M60000400073",
        "billId": 107880
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/rgd/2018/07/02/a562/jo/fr",
        "billId": 108416
      },
      {
        "state": "MN",
        "billNumber": "HF-4565",
        "billId": 1221
      },
      {
        "state": "NL",
        "billNumber": "BWBR0018139",
        "billId": 108243
      },
      {
        "state": "NL",
        "billNumber": "BWBR0032405",
        "billId": 108246
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1658",
        "billId": 108368
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/927",
        "billId": 108366
      },
      {
        "state": "SE",
        "billNumber": "sfs-2007-185",
        "billId": 108307
      },
      {
        "state": "SE",
        "billNumber": "sfs-2023-132",
        "billId": 108284
      },
      {
        "state": "SI",
        "billNumber": "2010-01-0111",
        "billId": 108434
      },
      {
        "state": "UK",
        "billNumber": "uksi/2015/63",
        "billId": 108163
      },
      {
        "state": "UY",
        "billNumber": "leyes/19829-2019",
        "billId": 111336
      },
      {
        "state": "VT",
        "billNumber": "H-915",
        "billId": 1213
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/283/made/en",
        "billId": 108323
      },
      {
        "state": "CN",
        "billNumber": "ff8081818d736e08018d786bd28914b5",
        "billId": 108480
      },
      {
        "state": "CN",
        "billNumber": "ff8080816f3e9784016f424f1b4a04d9",
        "billId": 108443
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2008-2387",
        "billId": 108270
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000044155771",
        "billId": 107980
      },
      {
        "state": "IN",
        "billNumber": "227250",
        "billId": 111389
      },
      {
        "state": "JP",
        "billNumber": "413M60000400063",
        "billId": 107906
      },
      {
        "state": "JP",
        "billNumber": "413M60000400074",
        "billId": 107887
      },
      {
        "state": "JP",
        "billNumber": "420M60000600001",
        "billId": 107931
      },
      {
        "state": "JP",
        "billNumber": "508M60001400003",
        "billId": 107943
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/2022/06/09/a266/jo/fr",
        "billId": 108413
      },
      {
        "state": "NL",
        "billNumber": "BWBR0024500",
        "billId": 108250
      },
      {
        "state": "SE",
        "billNumber": "sfs-1997-788",
        "billId": 108319
      },
      {
        "state": "UK",
        "billNumber": "uksi/1999/3447",
        "billId": 108137
      },
      {
        "state": "BR",
        "billNumber": "2629580",
        "billId": 111351
      },
      {
        "state": "CA",
        "billNumber": "111_97_pit",
        "billId": 108589
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127f631443681",
        "billId": 108444
      },
      {
        "state": "CN",
        "billNumber": "ff808181865edc140186d8920a3423b2",
        "billId": 108478
      },
      {
        "state": "CN",
        "billNumber": "ff808181927f127601936667b5d41015",
        "billId": 108465
      },
      {
        "state": "DE",
        "billNumber": "altholzv",
        "billId": 108227
      },
      {
        "state": "EE",
        "billNumber": "749804",
        "billId": 108417
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2022-5809",
        "billId": 108267
      },
      {
        "state": "EU",
        "billNumber": "32000L0053",
        "billId": 107263
      },
      {
        "state": "EU",
        "billNumber": "32005L0064",
        "billId": 107300
      },
      {
        "state": "EU",
        "billNumber": "32016L0585",
        "billId": 107447
      },
      {
        "state": "EU",
        "billNumber": "32025R0606",
        "billId": 107758
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000042837821",
        "billId": 107786
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000049375942",
        "billId": 107833
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000050749111",
        "billId": 107841
      },
      {
        "state": "JP",
        "billNumber": "413M60000400059",
        "billId": 107892
      },
      {
        "state": "JP",
        "billNumber": "413M60000400067",
        "billId": 107905
      },
      {
        "state": "JP",
        "billNumber": "413M60000400069",
        "billId": 107907
      },
      {
        "state": "JP",
        "billNumber": "413M60000400075",
        "billId": 107883
      },
      {
        "state": "JP",
        "billNumber": "413M60000C00004",
        "billId": 107914
      },
      {
        "state": "JP",
        "billNumber": "418M60000740001",
        "billId": 107928
      },
      {
        "state": "JP",
        "billNumber": "425M60001000005",
        "billId": 107932
      },
      {
        "state": "NY",
        "billNumber": "S-10168",
        "billId": 79613
      },
      {
        "state": "OR",
        "billNumber": "SB-123",
        "billId": 82818
      },
      {
        "state": "RI",
        "billNumber": "HB-5017",
        "billId": 80689
      },
      {
        "state": "SE",
        "billNumber": "sfs-2025-813",
        "billId": 108285
      },
      {
        "state": "UK",
        "billNumber": "uksi/2000/3097",
        "billId": 108168
      },
      {
        "state": "UK",
        "billNumber": "uksi/2003/2635",
        "billId": 108118
      },
      {
        "state": "UK",
        "billNumber": "uksi/2015/1935",
        "billId": 108159
      },
      {
        "state": "EU",
        "billNumber": "31997D0129",
        "billId": 107478
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/542",
        "billId": 108371
      },
      {
        "state": "DK",
        "billNumber": "lta/2019/1337",
        "billId": 108403
      },
      {
        "state": "CL",
        "billNumber": "1090894",
        "billId": 108275
      },
      {
        "state": "CN",
        "billNumber": "ff808181799def980179ad26f28814aa",
        "billId": 108463
      },
      {
        "state": "CN",
        "billNumber": "ff808181927f0931019325530cb6751c",
        "billId": 108464
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2006-9832",
        "billId": 108273
      },
      {
        "state": "EU",
        "billNumber": "32008L0033",
        "billId": 107517
      },
      {
        "state": "EU",
        "billNumber": "32017L2102",
        "billId": 107557
      },
      {
        "state": "EU",
        "billNumber": "32018L0849",
        "billId": 107511
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000052450618",
        "billId": 107972
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/281/made/en",
        "billId": 108325
      },
      {
        "state": "IN",
        "billNumber": "183723",
        "billId": 111390
      },
      {
        "state": "IN",
        "billNumber": "227293",
        "billId": 111391
      },
      {
        "state": "JP",
        "billNumber": "345AC0000000137",
        "billId": 107854
      },
      {
        "state": "JP",
        "billNumber": "413M60001500001",
        "billId": 107877
      },
      {
        "state": "LT",
        "billNumber": "TAIS.59267",
        "billId": 108428
      },
      {
        "state": "UY",
        "billNumber": "leyes/17849-2004",
        "billId": 111334
      },
      {
        "state": "BR",
        "billNumber": "_ato2023-2026/2025/decreto/D12688.htm",
        "billId": 108335
      },
      {
        "state": "CN",
        "billNumber": "ff80808175265dd40175f97b3fbc2377",
        "billId": 108447
      },
      {
        "state": "CN",
        "billNumber": "ff8081818b6b80c1018b6f0b15700b8e",
        "billId": 108468
      },
      {
        "state": "CN",
        "billNumber": "ff808181927f12760194167453206544",
        "billId": 108467
      },
      {
        "state": "CN",
        "billNumber": "ff80818194a5cf290194da1c80c547bb",
        "billId": 108481
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000029387124",
        "billId": 108010
      },
      {
        "state": "JP",
        "billNumber": "425M60001400003",
        "billId": 107933
      },
      {
        "state": "LV",
        "billNumber": "221378",
        "billId": 108420
      },
      {
        "state": "NY",
        "billNumber": "A-8195",
        "billId": 60357
      },
      {
        "state": "SE",
        "billNumber": "sfs-2007-186",
        "billId": 108308
      },
      {
        "state": "EU",
        "billNumber": "32018L0852",
        "billId": 107472
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000019074839",
        "billId": 107968
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000042753962",
        "billId": 107830
      },
      {
        "state": "CN",
        "billNumber": "zhengce/zhengceku/2021-02/22/content_5588274.htm",
        "billId": 108498
      },
      {
        "state": "CN",
        "billNumber": "ff8081818a1cb709018a24ff766d20df",
        "billId": 108469
      },
      {
        "state": "EU",
        "billNumber": "32026R0296",
        "billId": 107774
      },
      {
        "state": "LT",
        "billNumber": "TAIS.325345",
        "billId": 108431
      },
      {
        "state": "NL",
        "billNumber": "BWBR0046477",
        "billId": 108260
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/1648",
        "billId": 108352
      },
      {
        "state": "EU",
        "billNumber": "32025L1892",
        "billId": 107686
      },
      {
        "state": "BR",
        "billNumber": "_ato2023-2026/2023/decreto/D11413.htm",
        "billId": 108334
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/149/made/en",
        "billId": 108322
      },
      {
        "state": "PE",
        "billNumber": "ds-009-2019-minam",
        "billId": 111348
      },
      {
        "state": "EU",
        "billNumber": "32004D0249",
        "billId": 107401
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1587",
        "billId": 108344
      },
      {
        "state": "UK",
        "billNumber": "nisr/2023/25",
        "billId": 108158
      },
      {
        "state": "BR",
        "billNumber": "2614061",
        "billId": 111354
      },
      {
        "state": "CA",
        "billNumber": "AB-1311",
        "billId": 81168
      },
      {
        "state": "CA",
        "billNumber": "AB-1478",
        "billId": 80300
      },
      {
        "state": "EU",
        "billNumber": "32014D0955",
        "billId": 107497
      },
      {
        "state": "NL",
        "billNumber": "BWBR0050381",
        "billId": 108236
      },
      {
        "state": "NY",
        "billNumber": "S-7552",
        "billId": 60359
      },
      {
        "state": "SE",
        "billNumber": "sfs-2000-208",
        "billId": 108313
      },
      {
        "state": "MX",
        "billNumber": "LGPGIR",
        "billId": 111332
      },
      {
        "state": "SE",
        "billNumber": "sfs-2001-1063",
        "billId": 108312
      },
      {
        "state": "EU",
        "billNumber": "32001D0118",
        "billId": 107540
      },
      {
        "state": "UK",
        "billNumber": "uksi/2009/890",
        "billId": 108117
      },
      {
        "state": "JP",
        "billNumber": "508M60000740004",
        "billId": 107957
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/779",
        "billId": 108353
      },
      {
        "state": "MD",
        "billNumber": "SB-686",
        "billId": 72278
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/1403",
        "billId": 108356
      },
      {
        "state": "PL",
        "billNumber": "DU/2020/797",
        "billId": 108354
      },
      {
        "state": "UK",
        "billNumber": "uksi/2024/1332",
        "billId": 108115
      },
      {
        "state": "BR",
        "billNumber": "2314561",
        "billId": 111361
      },
      {
        "state": "CA",
        "billNumber": "SB-560",
        "billId": 720
      },
      {
        "state": "NY",
        "billNumber": "S-5663",
        "billId": 72875
      },
      {
        "state": "UK",
        "billNumber": "ukpga/2021/30",
        "billId": 108114
      },
      {
        "state": "IL",
        "billNumber": "SB-294",
        "billId": 81244
      }
    ]
  },
  {
    "lever": "compostability",
    "name": "Compostability",
    "headline": "Use certified-compostable materials where specified",
    "direction": "If compostable, label 'compostable only under industrial composting' per IS/ISO 17088:2021.",
    "focus": [
      "Packaging",
      "Organics",
      "Biobased",
      "Electronics",
      "Textiles",
      "Construction",
      "Batteries"
    ],
    "billCount": 29,
    "states": [
      "CA",
      "CN",
      "CZ",
      "EU",
      "FR",
      "IN",
      "JP",
      "PE",
      "PL",
      "UK",
      "UY",
      "WA"
    ],
    "evidence": {
      "state": "IN",
      "bill": "227249",
      "quote": "Compostable plastic packaging must bear label 'compostable only under industrial composting' and conform to IS/ISO 17088:2021"
    },
    "examples": [
      {
        "action": "If compostable, label 'compostable only under industrial composting' per IS/ISO 17088:2021.",
        "state": "IN",
        "billNumber": "227249",
        "billId": 111387,
        "quote": "Compostable plastic packaging must bear label 'compostable only under industrial composting' and conform to IS/ISO 17088:2021"
      },
      {
        "action": "Label carpet 'compostable' per Section 42357 to exempt from coverage.",
        "state": "CA",
        "billNumber": "AB-863",
        "billId": 79950,
        "quote": "Carpet that meets requirements of Section 42357 to be labeled 'compostable' is not a covered product"
      },
      {
        "action": "Use compostable green, agricultural, food, or vegetative materials to qualify for excluded activity exemption.",
        "state": "CA",
        "billNumber": "SB-279",
        "billId": 103008,
        "quote": "Composting of green material, agricultural material, food material, and vegetative food material (alone or in combination) with total feedstock and compost onsite not exceeding 200 cubic yards at any one time is an excluded activity (no permit required)"
      }
    ],
    "feeImpact": {
      "malus": false,
      "bonus": true,
      "setJurisdictions": [
        "FR"
      ],
      "usPending": true,
      "examples": [
        {
          "jurisdiction": "FR",
          "amount": "25.0 euros/tonne"
        }
      ]
    },
    "bills": [
      {
        "state": "IN",
        "billNumber": "227249",
        "billId": 111387
      },
      {
        "state": "CA",
        "billNumber": "AB-863",
        "billId": 79950
      },
      {
        "state": "CA",
        "billNumber": "SB-279",
        "billId": 103008
      },
      {
        "state": "CA",
        "billNumber": "regulation/210391",
        "billId": 108593
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000041553759",
        "billId": 107838
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000042753962",
        "billId": 107830
      },
      {
        "state": "PE",
        "billNumber": "ley-30884",
        "billId": 111349
      },
      {
        "state": "CA",
        "billNumber": "SB-54",
        "billId": 865
      },
      {
        "state": "CN",
        "billNumber": "ff80808175265dd40176b843949f3d0c",
        "billId": 108475
      },
      {
        "state": "UY",
        "billNumber": "leyes/19829-2019",
        "billId": 111336
      },
      {
        "state": "CA",
        "billNumber": "SB-343",
        "billId": 81917
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127e112bb1ff4",
        "billId": 108449
      },
      {
        "state": "EU",
        "billNumber": "32025R0040",
        "billId": 107258
      },
      {
        "state": "EU",
        "billNumber": "32018L0852",
        "billId": 107472
      },
      {
        "state": "IN",
        "billNumber": "183721",
        "billId": 111386
      },
      {
        "state": "CN",
        "billNumber": "ff8081818a1cb709018a24ff766d20df",
        "billId": 108469
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000027947087",
        "billId": 108029
      },
      {
        "state": "EU",
        "billNumber": "32001D0524",
        "billId": 107336
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032187830",
        "billId": 108011
      },
      {
        "state": "UK",
        "billNumber": "wsi/2011/551",
        "billId": 108196
      },
      {
        "state": "CZ",
        "billNumber": "2020/541",
        "billId": 108438
      },
      {
        "state": "WA",
        "billNumber": "SB-5284",
        "billId": 104217
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000036396791",
        "billId": 108018
      },
      {
        "state": "JP",
        "billNumber": "413M60001200002",
        "billId": 107919
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/1648",
        "billId": 108352
      },
      {
        "state": "UK",
        "billNumber": "ukpga/2003/29",
        "billId": 108183
      },
      {
        "state": "UK",
        "billNumber": "nisr/2020/285",
        "billId": 108144
      },
      {
        "state": "CA",
        "billNumber": "AB-1857",
        "billId": 82616
      },
      {
        "state": "EU",
        "billNumber": "31999L0031",
        "billId": 107296
      }
    ]
  },
  {
    "lever": "repairability_durability",
    "name": "Repairability & Durability",
    "headline": "Design for repairability, spare-parts access, and longevity",
    "direction": "Ensure spare parts availability for product reuse, refurbishment, lifetime extension.",
    "focus": [
      "Packaging",
      "Electronics",
      "Batteries",
      "Hazardous materials",
      "Textiles",
      "Vehicles",
      "Organics"
    ],
    "billCount": 147,
    "states": [
      "AT",
      "CA",
      "CL",
      "CN",
      "CO",
      "CT",
      "CZ",
      "DE",
      "DK",
      "ES",
      "EU",
      "FI",
      "FR",
      "IE",
      "IN",
      "JP",
      "KY",
      "LT",
      "LU",
      "ME",
      "MN",
      "NL",
      "NY",
      "OR",
      "PL",
      "RI",
      "SC",
      "SE",
      "SI",
      "UK",
      "VT",
      "WA"
    ],
    "evidence": {
      "state": "EU",
      "bill": "32011L0065",
      "quote": "Ensure spare parts are available for product reuse, refurbishment, and lifetime extension"
    },
    "examples": [
      {
        "action": "Ensure spare parts availability for product reuse, refurbishment, lifetime extension.",
        "state": "EU",
        "billNumber": "32011L0065",
        "billId": 107355,
        "quote": "Ensure spare parts are available for product reuse, refurbishment, and lifetime extension"
      },
      {
        "action": "Adopt highly durable compressors and standardize parts across models.",
        "state": "JP",
        "billNumber": "413M60000400063",
        "billId": 107906,
        "quote": "Promote long-term use by adopting highly durable compressors and other long-life parts, and by standardizing circuit boards and other parts across different models to facilitate repair"
      },
      {
        "action": "Adopt highly durable drive units and long-life parts.",
        "state": "JP",
        "billNumber": "413M60000400070",
        "billId": 107886,
        "quote": "Promote long-term use by adopting highly durable drive units and other long-life parts, and by standardizing circuit boards and other parts across different models to facilitate repair"
      }
    ],
    "feeImpact": {
      "malus": false,
      "bonus": true,
      "setJurisdictions": [
        "CL",
        "ES",
        "EU",
        "FR",
        "NL",
        "PL"
      ],
      "usPending": true,
      "examples": []
    },
    "bills": [
      {
        "state": "EU",
        "billNumber": "32011L0065",
        "billId": 107355
      },
      {
        "state": "JP",
        "billNumber": "413M60000400063",
        "billId": 107906
      },
      {
        "state": "JP",
        "billNumber": "413M60000400070",
        "billId": 107886
      },
      {
        "state": "JP",
        "billNumber": "413M60000400072",
        "billId": 107882
      },
      {
        "state": "JP",
        "billNumber": "413M60000400073",
        "billId": 107880
      },
      {
        "state": "OR",
        "billNumber": "SB-550",
        "billId": 83232
      },
      {
        "state": "NY",
        "billNumber": "S-5027C",
        "billId": 104184
      },
      {
        "state": "FI",
        "billNumber": "2021/714",
        "billId": 108406
      },
      {
        "state": "CA",
        "billNumber": "SB-1384",
        "billId": 82737
      },
      {
        "state": "CA",
        "billNumber": "SB-244",
        "billId": 82438
      },
      {
        "state": "CO",
        "billNumber": "HB-22-1031",
        "billId": 82800
      },
      {
        "state": "CO",
        "billNumber": "HB-23-1011",
        "billId": 79666
      },
      {
        "state": "CO",
        "billNumber": "HB-24-1121",
        "billId": 81480
      },
      {
        "state": "CT",
        "billNumber": "HB-6512",
        "billId": 72465
      },
      {
        "state": "CT",
        "billNumber": "SB-308",
        "billId": 81673
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2025-17186",
        "billId": 108272
      },
      {
        "state": "EU",
        "billNumber": "32024R1781",
        "billId": 107265
      },
      {
        "state": "FI",
        "billNumber": "2011/646",
        "billId": 108405
      },
      {
        "state": "FI",
        "billNumber": "2014/519",
        "billId": 108407
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000029881868",
        "billId": 108048
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032610837",
        "billId": 107843
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000042837821",
        "billId": 107786
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000044513913",
        "billId": 107809
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000044806559",
        "billId": 108045
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000044806569",
        "billId": 107792
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000045072860",
        "billId": 108046
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047476652",
        "billId": 107811
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000049375942",
        "billId": 107833
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000050000979",
        "billId": 107790
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10",
        "billId": 108100
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-4",
        "billId": 108097
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000110",
        "billId": 107855
      },
      {
        "state": "JP",
        "billNumber": "413M60000400062",
        "billId": 107908
      },
      {
        "state": "JP",
        "billNumber": "413M60000400064",
        "billId": 107912
      },
      {
        "state": "JP",
        "billNumber": "413M60000400065",
        "billId": 107909
      },
      {
        "state": "JP",
        "billNumber": "413M60000400066",
        "billId": 107911
      },
      {
        "state": "JP",
        "billNumber": "413M60000400067",
        "billId": 107905
      },
      {
        "state": "JP",
        "billNumber": "413M60000400068",
        "billId": 107910
      },
      {
        "state": "JP",
        "billNumber": "413M60000400069",
        "billId": 107907
      },
      {
        "state": "JP",
        "billNumber": "413M60000400071",
        "billId": 107878
      },
      {
        "state": "JP",
        "billNumber": "413M60000400074",
        "billId": 107887
      },
      {
        "state": "JP",
        "billNumber": "413M60000400075",
        "billId": 107883
      },
      {
        "state": "JP",
        "billNumber": "413M60000400079",
        "billId": 107881
      },
      {
        "state": "JP",
        "billNumber": "413M60000C00004",
        "billId": 107914
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/2022/06/09/a266/jo/fr",
        "billId": 108413
      },
      {
        "state": "ME",
        "billNumber": "LD-1487",
        "billId": 72511
      },
      {
        "state": "ME",
        "billNumber": "LD-2211",
        "billId": 72480
      },
      {
        "state": "MN",
        "billNumber": "SF-1598",
        "billId": 81821
      },
      {
        "state": "NY",
        "billNumber": "S-4104",
        "billId": 81072
      },
      {
        "state": "OR",
        "billNumber": "SB-1596",
        "billId": 72344
      },
      {
        "state": "RI",
        "billNumber": "HB-5017",
        "billId": 80689
      },
      {
        "state": "RI",
        "billNumber": "SB-884",
        "billId": 80226
      },
      {
        "state": "SE",
        "billNumber": "sfs-2005-209",
        "billId": 108311
      },
      {
        "state": "DE",
        "billNumber": "battdg",
        "billId": 108220
      },
      {
        "state": "JP",
        "billNumber": "413M60000400076",
        "billId": 107885
      },
      {
        "state": "JP",
        "billNumber": "413M60000400080",
        "billId": 107903
      },
      {
        "state": "JP",
        "billNumber": "413M60000C00001",
        "billId": 107913
      },
      {
        "state": "NL",
        "billNumber": "BWBR0007227",
        "billId": 108248
      },
      {
        "state": "UK",
        "billNumber": "uksi/1994/232",
        "billId": 108170
      },
      {
        "state": "NL",
        "billNumber": "BWBR0034782",
        "billId": 108245
      },
      {
        "state": "AT",
        "billNumber": "20005815",
        "billId": 108330
      },
      {
        "state": "CN",
        "billNumber": "ff808181865edc140186d8920a3423b2",
        "billId": 108478
      },
      {
        "state": "CN",
        "billNumber": "zhengce/content/2017-01/03/content_5156043.htm",
        "billId": 108496
      },
      {
        "state": "DE",
        "billNumber": "elektrog_2015",
        "billId": 108218
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2008-2387",
        "billId": 108270
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000026863961",
        "billId": 108044
      },
      {
        "state": "NL",
        "billNumber": "BWBR0017053",
        "billId": 108247
      },
      {
        "state": "PL",
        "billNumber": "DU/2014/1322",
        "billId": 108397
      },
      {
        "state": "PL",
        "billNumber": "DU/2022/1113",
        "billId": 108388
      },
      {
        "state": "SI",
        "billNumber": "2010-01-0111",
        "billId": 108434
      },
      {
        "state": "UK",
        "billNumber": "uksi/2015/63",
        "billId": 108163
      },
      {
        "state": "NL",
        "billNumber": "BWBR0044197",
        "billId": 108234
      },
      {
        "state": "DK",
        "billNumber": "lta/2014/130",
        "billId": 108401
      },
      {
        "state": "EU",
        "billNumber": "32016L0585",
        "billId": 107447
      },
      {
        "state": "JP",
        "billNumber": "413M60000400083",
        "billId": 107897
      },
      {
        "state": "JP",
        "billNumber": "504M60007FFE001",
        "billId": 107937
      },
      {
        "state": "JP",
        "billNumber": "508M60000400011",
        "billId": 107949
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/573",
        "billId": 108376
      },
      {
        "state": "JP",
        "billNumber": "413M60001400001",
        "billId": 107915
      },
      {
        "state": "EU",
        "billNumber": "32012L0019",
        "billId": 107259
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-3",
        "billId": 108104
      },
      {
        "state": "CN",
        "billNumber": "zhengce/zhengceku/2017-01/03/content_5156043.htm",
        "billId": 108497
      },
      {
        "state": "EU",
        "billNumber": "32020L0363",
        "billId": 107370
      },
      {
        "state": "JP",
        "billNumber": "508M60000400008",
        "billId": 107948
      },
      {
        "state": "CO",
        "billNumber": "SB-25-163",
        "billId": 82272
      },
      {
        "state": "EU",
        "billNumber": "32018L0852",
        "billId": 107472
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/2151",
        "billId": 108350
      },
      {
        "state": "CA",
        "billNumber": "AB-962",
        "billId": 79926
      },
      {
        "state": "EU",
        "billNumber": "32009R0641",
        "billId": 107299
      },
      {
        "state": "EU",
        "billNumber": "32017L2102",
        "billId": 107557
      },
      {
        "state": "EU",
        "billNumber": "32026R0296",
        "billId": 107774
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000045072868",
        "billId": 107810
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-24",
        "billId": 108110
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-26",
        "billId": 108112
      },
      {
        "state": "JP",
        "billNumber": "405M50000400034",
        "billId": 107870
      },
      {
        "state": "JP",
        "billNumber": "405M50000500001",
        "billId": 107869
      },
      {
        "state": "JP",
        "billNumber": "410AC0000000097",
        "billId": 107691
      },
      {
        "state": "UK",
        "billNumber": "nisr/2006/519",
        "billId": 108153
      },
      {
        "state": "CT",
        "billNumber": "HB-5019",
        "billId": 81565
      },
      {
        "state": "KY",
        "billNumber": "SB-49",
        "billId": 80507
      },
      {
        "state": "NL",
        "billNumber": "BWBR0016990",
        "billId": 108244
      },
      {
        "state": "OR",
        "billNumber": "HB-4144",
        "billId": 82947
      },
      {
        "state": "WA",
        "billNumber": "SB-5144",
        "billId": 104189
      },
      {
        "state": "ME",
        "billNumber": "LD-474",
        "billId": 104191
      },
      {
        "state": "NL",
        "billNumber": "BWBR0032405",
        "billId": 108246
      },
      {
        "state": "CA",
        "billNumber": "regulation/200522",
        "billId": 108594
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2015-1762",
        "billId": 108269
      },
      {
        "state": "MN",
        "billNumber": "HF-4565",
        "billId": 1221
      },
      {
        "state": "NL",
        "billNumber": "BWBR0048299",
        "billId": 108235
      },
      {
        "state": "SC",
        "billNumber": "S-171",
        "billId": 104219
      },
      {
        "state": "DK",
        "billNumber": "lta/2019/1337",
        "billId": 108403
      },
      {
        "state": "LT",
        "billNumber": "TAIS.59267",
        "billId": 108428
      },
      {
        "state": "CN",
        "billNumber": "ff8080816f3e9784016f424f1b4a04d9",
        "billId": 108443
      },
      {
        "state": "EU",
        "billNumber": "32025L1892",
        "billId": 107686
      },
      {
        "state": "EU",
        "billNumber": "32005L0064",
        "billId": 107300
      },
      {
        "state": "EU",
        "billNumber": "32019D0665",
        "billId": 107609
      },
      {
        "state": "JP",
        "billNumber": "403AC0000000048",
        "billId": 107692
      },
      {
        "state": "SI",
        "billNumber": "2024-01-2498",
        "billId": 108435
      },
      {
        "state": "UK",
        "billNumber": "uksi/2005/263",
        "billId": 108130
      },
      {
        "state": "CO",
        "billNumber": "HB-22-1355",
        "billId": 72416
      },
      {
        "state": "JP",
        "billNumber": "508M60001400003",
        "billId": 107943
      },
      {
        "state": "ME",
        "billNumber": "LD-1423",
        "billId": 80310
      },
      {
        "state": "JP",
        "billNumber": "508M60000400007",
        "billId": 107946
      },
      {
        "state": "JP",
        "billNumber": "508M60000400009",
        "billId": 107947
      },
      {
        "state": "JP",
        "billNumber": "508M60000400010",
        "billId": 107951
      },
      {
        "state": "CA",
        "billNumber": "SB-707",
        "billId": 620
      },
      {
        "state": "JP",
        "billNumber": "503AC0000000060",
        "billId": 107694
      },
      {
        "state": "UK",
        "billNumber": "wsi/2011/551",
        "billId": 108196
      },
      {
        "state": "VT",
        "billNumber": "S-254",
        "billId": 81811
      },
      {
        "state": "CL",
        "billNumber": "1154847",
        "billId": 108276
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000029387124",
        "billId": 108010
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000042575740",
        "billId": 107805
      },
      {
        "state": "IN",
        "billNumber": "227250",
        "billId": 111389
      },
      {
        "state": "EU",
        "billNumber": "32008L0098",
        "billId": 107264
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047439314",
        "billId": 107851
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000052450618",
        "billId": 107972
      },
      {
        "state": "DE",
        "billNumber": "krwg",
        "billId": 108221
      },
      {
        "state": "JP",
        "billNumber": "425M60001400003",
        "billId": 107933
      },
      {
        "state": "EU",
        "billNumber": "32019D2193",
        "billId": 107624
      },
      {
        "state": "NY",
        "billNumber": "A-6193",
        "billId": 60356
      },
      {
        "state": "CZ",
        "billNumber": "2020/542",
        "billId": 108439
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/149/made/en",
        "billId": 108322
      },
      {
        "state": "SE",
        "billNumber": "sfs-2023-133",
        "billId": 108283
      },
      {
        "state": "NL",
        "billNumber": "BWBR0045640",
        "billId": 108238
      },
      {
        "state": "ME",
        "billNumber": "LD-1519",
        "billId": 81678
      },
      {
        "state": "CN",
        "billNumber": "4028abcc61277793016127da36ca191c",
        "billId": 108448
      },
      {
        "state": "JP",
        "billNumber": "508M60001740001",
        "billId": 107955
      }
    ]
  }
];
