// AUTO-GENERATED from tmp/design_principles.json by scripts/generate_design_teaser.py. Do not edit by hand.
// The Free teaser: per-lever headline + direction + material/product focus (front face),
// plus the grounded source bills behind the principle (back face -- each opens the bill modal).

export interface TeaserBill {
  state: string;
  billNumber: string;
  billId: number;
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
  feeImpact: FeeImpact | null;
  bills: TeaserBill[];
}

export const GUIDE_COVERAGE = {"bills": 471, "states": 35, "levers": 9};

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
      "Hazardous materials",
      "Organics",
      "Vehicles",
      "Textiles"
    ],
    "billCount": 296,
    "states": [
      "AT",
      "BR",
      "CH",
      "CL",
      "CO",
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
      "JP",
      "LT",
      "LU",
      "LV",
      "MA",
      "MN",
      "NJ",
      "NL",
      "NY",
      "OR",
      "PL",
      "SC",
      "SE",
      "SI",
      "SK",
      "UK",
      "WA"
    ],
    "evidence": {
      "state": "PL",
      "bill": "DU/2019/542",
      "quote": "Design and manufacture packaging to enable reuse and subsequent recycling, or at minimum recycling, or other recovery if recycling is not possible"
    },
    "feeImpact": {
      "malus": true,
      "bonus": true,
      "setJurisdictions": [
        "CL",
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
        "billId": 9996
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/927",
        "billId": 9991
      },
      {
        "state": "AT",
        "billNumber": "20008902",
        "billId": 9953
      },
      {
        "state": "JP",
        "billNumber": "413M60000400090",
        "billId": 9515
      },
      {
        "state": "NY",
        "billNumber": "S-5027C",
        "billId": 1100
      },
      {
        "state": "DE",
        "billNumber": "altautov",
        "billId": 9847
      },
      {
        "state": "DE",
        "billNumber": "elektrog_2015",
        "billId": 9843
      },
      {
        "state": "DK",
        "billNumber": "lta/2014/130",
        "billId": 10026
      },
      {
        "state": "DK",
        "billNumber": "lta/2015/1453",
        "billId": 10027
      },
      {
        "state": "DK",
        "billNumber": "lta/2019/1218",
        "billId": 10029
      },
      {
        "state": "EE",
        "billNumber": "113032019103",
        "billId": 10043
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2008-2387",
        "billId": 9895
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2021-5868",
        "billId": 9896
      },
      {
        "state": "EU",
        "billNumber": "31994L0062",
        "billId": 5
      },
      {
        "state": "EU",
        "billNumber": "31999D0823",
        "billId": 431
      },
      {
        "state": "EU",
        "billNumber": "32000L0053",
        "billId": 6
      },
      {
        "state": "EU",
        "billNumber": "32001D0753",
        "billId": 608
      },
      {
        "state": "EU",
        "billNumber": "32004D0249",
        "billId": 556
      },
      {
        "state": "EU",
        "billNumber": "32005L0064",
        "billId": 455
      },
      {
        "state": "EU",
        "billNumber": "32006L0066",
        "billId": 504
      },
      {
        "state": "EU",
        "billNumber": "32009L0001",
        "billId": 541
      },
      {
        "state": "EU",
        "billNumber": "32018L0852",
        "billId": 627
      },
      {
        "state": "EU",
        "billNumber": "32024R1781",
        "billId": 8
      },
      {
        "state": "EU",
        "billNumber": "32025R0040",
        "billId": 1
      },
      {
        "state": "FI",
        "billNumber": "2014/519",
        "billId": 10032
      },
      {
        "state": "FI",
        "billNumber": "2021/714",
        "billId": 10031
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043458675",
        "billId": 9440
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000046285336",
        "billId": 9584
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000046664100",
        "billId": 9454
      },
      {
        "state": "JP",
        "billNumber": "405M50000400034",
        "billId": 9495
      },
      {
        "state": "JP",
        "billNumber": "405M50000500001",
        "billId": 9494
      },
      {
        "state": "JP",
        "billNumber": "407M50000100061",
        "billId": 9496
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000110",
        "billId": 9480
      },
      {
        "state": "JP",
        "billNumber": "413M60000400078",
        "billId": 9509
      },
      {
        "state": "JP",
        "billNumber": "413M60000400079",
        "billId": 9506
      },
      {
        "state": "JP",
        "billNumber": "413M60000400080",
        "billId": 9528
      },
      {
        "state": "JP",
        "billNumber": "413M60000400082",
        "billId": 9524
      },
      {
        "state": "JP",
        "billNumber": "413M60000400083",
        "billId": 9522
      },
      {
        "state": "JP",
        "billNumber": "413M60000400084",
        "billId": 9529
      },
      {
        "state": "JP",
        "billNumber": "413M60000400085",
        "billId": 9525
      },
      {
        "state": "JP",
        "billNumber": "413M60000400086",
        "billId": 9527
      },
      {
        "state": "JP",
        "billNumber": "413M60000400087",
        "billId": 9521
      },
      {
        "state": "JP",
        "billNumber": "413M60000400088",
        "billId": 9526
      },
      {
        "state": "JP",
        "billNumber": "413M60000400089",
        "billId": 9523
      },
      {
        "state": "JP",
        "billNumber": "413M60000400091",
        "billId": 9513
      },
      {
        "state": "JP",
        "billNumber": "413M60000400092",
        "billId": 9514
      },
      {
        "state": "JP",
        "billNumber": "413M60000C00001",
        "billId": 9538
      },
      {
        "state": "JP",
        "billNumber": "413M60001500001",
        "billId": 9502
      },
      {
        "state": "JP",
        "billNumber": "424AC0000000057",
        "billId": 845
      },
      {
        "state": "JP",
        "billNumber": "506AC0000000041",
        "billId": 9478
      },
      {
        "state": "JP",
        "billNumber": "508M60001400002",
        "billId": 9569
      },
      {
        "state": "JP",
        "billNumber": "508M60001440001",
        "billId": 9570
      },
      {
        "state": "LT",
        "billNumber": "TAIS.161216",
        "billId": 10054
      },
      {
        "state": "NL",
        "billNumber": "BWBR0016459",
        "billId": 9881
      },
      {
        "state": "NL",
        "billNumber": "BWBR0017053",
        "billId": 9872
      },
      {
        "state": "NL",
        "billNumber": "BWBR0018139",
        "billId": 9868
      },
      {
        "state": "NL",
        "billNumber": "BWBR0048093",
        "billId": 9858
      },
      {
        "state": "NY",
        "billNumber": "S-5062",
        "billId": 3596
      },
      {
        "state": "OR",
        "billNumber": "HB-3780",
        "billId": 3692
      },
      {
        "state": "PL",
        "billNumber": "DU/2015/687",
        "billId": 10021
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/150",
        "billId": 9997
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/521",
        "billId": 10017
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/160",
        "billId": 9994
      },
      {
        "state": "SE",
        "billNumber": "sfs-1997-185",
        "billId": 9945
      },
      {
        "state": "SE",
        "billNumber": "sfs-2006-1273",
        "billId": 9934
      },
      {
        "state": "SE",
        "billNumber": "sfs-2007-185",
        "billId": 9932
      },
      {
        "state": "SE",
        "billNumber": "sfs-2014-1073",
        "billId": 9924
      },
      {
        "state": "SE",
        "billNumber": "sfs-2018-1462",
        "billId": 9919
      },
      {
        "state": "SE",
        "billNumber": "sfs-2023-132",
        "billId": 9909
      },
      {
        "state": "UK",
        "billNumber": "uksi/1999/3447",
        "billId": 9762
      },
      {
        "state": "UK",
        "billNumber": "uksi/2003/2635",
        "billId": 9743
      },
      {
        "state": "UK",
        "billNumber": "uksi/2020/904",
        "billId": 9768
      },
      {
        "state": "DE",
        "billNumber": "battdg",
        "billId": 9845
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032847905",
        "billId": 9439
      },
      {
        "state": "MN",
        "billNumber": "HF-3911",
        "billId": 4980
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-3",
        "billId": 9729
      },
      {
        "state": "NL",
        "billNumber": "BWBR0048299",
        "billId": 9860
      },
      {
        "state": "PL",
        "billNumber": "DU/2013/888",
        "billId": 10000
      },
      {
        "state": "PL",
        "billNumber": "DU/2020/1114",
        "billId": 9995
      },
      {
        "state": "FI",
        "billNumber": "2014/520",
        "billId": 10033
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1658",
        "billId": 9993
      },
      {
        "state": "EU",
        "billNumber": "32009D0292",
        "billId": 684
      },
      {
        "state": "JP",
        "billNumber": "413M60000400050",
        "billId": 9520
      },
      {
        "state": "JP",
        "billNumber": "420M60000600001",
        "billId": 9556
      },
      {
        "state": "JP",
        "billNumber": "425M60001400003",
        "billId": 9558
      },
      {
        "state": "JP",
        "billNumber": "508M60001400003",
        "billId": 9568
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/2022/06/09/a266/jo/fr",
        "billId": 10038
      },
      {
        "state": "NL",
        "billNumber": "BWBR0013707",
        "billId": 9883
      },
      {
        "state": "PL",
        "billNumber": "DU/2020/1893",
        "billId": 10004
      },
      {
        "state": "WA",
        "billNumber": "SB-5144",
        "billId": 993
      },
      {
        "state": "CL",
        "billNumber": "1223902",
        "billId": 9903
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047483124",
        "billId": 9431
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-18",
        "billId": 9731
      },
      {
        "state": "NL",
        "billNumber": "BWBR0044197",
        "billId": 9859
      },
      {
        "state": "CH",
        "billNumber": "cc/2000/299",
        "billId": 9965
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2006-9832",
        "billId": 9898
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2022-5809",
        "billId": 9892
      },
      {
        "state": "EU",
        "billNumber": "32008D0440",
        "billId": 442
      },
      {
        "state": "EU",
        "billNumber": "32009R0641",
        "billId": 454
      },
      {
        "state": "EU",
        "billNumber": "32023D1060",
        "billId": 874
      },
      {
        "state": "FI",
        "billNumber": "2011/646",
        "billId": 10030
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-11",
        "billId": 9717
      },
      {
        "state": "JP",
        "billNumber": "413M60000400059",
        "billId": 9517
      },
      {
        "state": "JP",
        "billNumber": "414M60001400007",
        "billId": 9548
      },
      {
        "state": "JP",
        "billNumber": "508M60000400007",
        "billId": 9571
      },
      {
        "state": "JP",
        "billNumber": "508M60000400008",
        "billId": 9573
      },
      {
        "state": "JP",
        "billNumber": "508M60000400009",
        "billId": 9572
      },
      {
        "state": "JP",
        "billNumber": "508M60000400010",
        "billId": 9576
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/2017/03/21/a330/jo/fr",
        "billId": 10037
      },
      {
        "state": "LV",
        "billNumber": "57207",
        "billId": 10046
      },
      {
        "state": "NL",
        "billNumber": "BWBR0037392",
        "billId": 9866
      },
      {
        "state": "PL",
        "billNumber": "DU/2009/666",
        "billId": 10023
      },
      {
        "state": "PL",
        "billNumber": "DU/2015/1688",
        "billId": 10008
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/1895",
        "billId": 10005
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/573",
        "billId": 10001
      },
      {
        "state": "SE",
        "billNumber": "sfs-1997-788",
        "billId": 9944
      },
      {
        "state": "UK",
        "billNumber": "uksi/2016/1146",
        "billId": 9748
      },
      {
        "state": "CL",
        "billNumber": "1157019",
        "billId": 9902
      },
      {
        "state": "EU",
        "billNumber": "32012L0019",
        "billId": 2
      },
      {
        "state": "EE",
        "billNumber": "749804",
        "billId": 10042
      },
      {
        "state": "EU",
        "billNumber": "32018L0849",
        "billId": 666
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-17",
        "billId": 9724
      },
      {
        "state": "JP",
        "billNumber": "508M60000400011",
        "billId": 9574
      },
      {
        "state": "JP",
        "billNumber": "508M60000740002",
        "billId": 9578
      },
      {
        "state": "LV",
        "billNumber": "267716",
        "billId": 10048
      },
      {
        "state": "NL",
        "billNumber": "BWBR0034782",
        "billId": 9870
      },
      {
        "state": "PL",
        "billNumber": "DU/2005/1495",
        "billId": 10011
      },
      {
        "state": "PL",
        "billNumber": "DU/2017/2056",
        "billId": 9998
      },
      {
        "state": "SI",
        "billNumber": "2021-01-1053",
        "billId": 10057
      },
      {
        "state": "JP",
        "billNumber": "403AC0000000048",
        "billId": 847
      },
      {
        "state": "BR",
        "billNumber": "_ato2023-2026/2023/decreto/D11413.htm",
        "billId": 9959
      },
      {
        "state": "BR",
        "billNumber": "_ato2023-2026/2025/decreto/D12688.htm",
        "billId": 9960
      },
      {
        "state": "CH",
        "billNumber": "cc/2021/633",
        "billId": 9962
      },
      {
        "state": "CO",
        "billNumber": "HB22-1355",
        "billId": 4979
      },
      {
        "state": "CZ",
        "billNumber": "2020/542",
        "billId": 10064
      },
      {
        "state": "DE",
        "billNumber": "altholzv",
        "billId": 9852
      },
      {
        "state": "DE",
        "billNumber": "krwg",
        "billId": 9846
      },
      {
        "state": "DK",
        "billNumber": "lta/2019/1337",
        "billId": 10028
      },
      {
        "state": "EU",
        "billNumber": "31999D0042",
        "billId": 607
      },
      {
        "state": "EU",
        "billNumber": "31999D0652",
        "billId": 551
      },
      {
        "state": "EU",
        "billNumber": "32001D0524",
        "billId": 491
      },
      {
        "state": "EU",
        "billNumber": "32002D0204",
        "billId": 697
      },
      {
        "state": "EU",
        "billNumber": "32004L0012",
        "billId": 533
      },
      {
        "state": "EU",
        "billNumber": "32018L0851",
        "billId": 449
      },
      {
        "state": "EU",
        "billNumber": "32021D1752",
        "billId": 773
      },
      {
        "state": "EU",
        "billNumber": "32025R0351",
        "billId": 868
      },
      {
        "state": "FI",
        "billNumber": "2021/1029",
        "billId": 10034
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000025423069",
        "billId": 9667
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000029387124",
        "billId": 9635
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032187830",
        "billId": 9636
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043799891",
        "billId": 9615
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000053625694",
        "billId": 9457
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10",
        "billId": 9725
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-1",
        "billId": 9721
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-12",
        "billId": 9727
      },
      {
        "state": "IE",
        "billNumber": "eli/2007/si/798/made/en",
        "billId": 9951
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/281/made/en",
        "billId": 9950
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/282/made/en",
        "billId": 9949
      },
      {
        "state": "JP",
        "billNumber": "345AC0000000137",
        "billId": 9479
      },
      {
        "state": "JP",
        "billNumber": "410AC0000000097",
        "billId": 846
      },
      {
        "state": "JP",
        "billNumber": "410CO0000000378",
        "billId": 9484
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000104",
        "billId": 852
      },
      {
        "state": "JP",
        "billNumber": "413CO0000000176",
        "billId": 9486
      },
      {
        "state": "JP",
        "billNumber": "413M60001400001",
        "billId": 9540
      },
      {
        "state": "JP",
        "billNumber": "413M60001F40004",
        "billId": 9546
      },
      {
        "state": "JP",
        "billNumber": "503AC0000000060",
        "billId": 849
      },
      {
        "state": "JP",
        "billNumber": "504M60000F42001",
        "billId": 9563
      },
      {
        "state": "JP",
        "billNumber": "504M60001400001",
        "billId": 9565
      },
      {
        "state": "JP",
        "billNumber": "504M60007FFE001",
        "billId": 9562
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/rgd/2018/07/02/a562/jo/fr",
        "billId": 10041
      },
      {
        "state": "LV",
        "billNumber": "124707",
        "billId": 10047
      },
      {
        "state": "LV",
        "billNumber": "221378",
        "billId": 10045
      },
      {
        "state": "NJ",
        "billNumber": "S-3399",
        "billId": 2385
      },
      {
        "state": "NL",
        "billNumber": "BWBR0016038",
        "billId": 9880
      },
      {
        "state": "NL",
        "billNumber": "BWBR0024500",
        "billId": 9875
      },
      {
        "state": "PL",
        "billNumber": "DU/2008/1464",
        "billId": 10010
      },
      {
        "state": "PL",
        "billNumber": "DU/2016/1863",
        "billId": 9999
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/1834",
        "billId": 9968
      },
      {
        "state": "SE",
        "billNumber": "sfs-1998-808",
        "billId": 9943
      },
      {
        "state": "SE",
        "billNumber": "sfs-2001-1063",
        "billId": 9937
      },
      {
        "state": "SI",
        "billNumber": "2015-01-1513",
        "billId": 10058
      },
      {
        "state": "UK",
        "billNumber": "nisr/2020/285",
        "billId": 9769
      },
      {
        "state": "UK",
        "billNumber": "ssi/2000/451",
        "billId": 9761
      },
      {
        "state": "UK",
        "billNumber": "uksi/2000/3375",
        "billId": 9760
      },
      {
        "state": "UK",
        "billNumber": "uksi/2012/3082",
        "billId": 9751
      },
      {
        "state": "UK",
        "billNumber": "uksi/2023/1244",
        "billId": 9745
      },
      {
        "state": "UK",
        "billNumber": "uksi/2025/1369",
        "billId": 9744
      },
      {
        "state": "EE",
        "billNumber": "918053",
        "billId": 10044
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2015-1762",
        "billId": 9894
      },
      {
        "state": "EU",
        "billNumber": "32025L1892",
        "billId": 841
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000026863961",
        "billId": 9669
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000027947087",
        "billId": 9654
      },
      {
        "state": "NY",
        "billNumber": "A-6193",
        "billId": 3105
      },
      {
        "state": "NY",
        "billNumber": "S-3217",
        "billId": 3115
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-1001",
        "billId": 9915
      },
      {
        "state": "EU",
        "billNumber": "32023D2683",
        "billId": 883
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000041553759",
        "billId": 9463
      },
      {
        "state": "SE",
        "billNumber": "sfs-2005-209",
        "billId": 9936
      },
      {
        "state": "EU",
        "billNumber": "32021R0770",
        "billId": 737
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/1466",
        "billId": 10006
      },
      {
        "state": "AT",
        "billNumber": "20002086",
        "billId": 9952
      },
      {
        "state": "BR",
        "billNumber": "_ato2007-2010/2010/lei/l12305.htm",
        "billId": 9957
      },
      {
        "state": "CL",
        "billNumber": "1208163",
        "billId": 9904
      },
      {
        "state": "EU",
        "billNumber": "32012R1179",
        "billId": 646
      },
      {
        "state": "EU",
        "billNumber": "32026R0296",
        "billId": 929
      },
      {
        "state": "NY",
        "billNumber": "S-7552",
        "billId": 3378
      },
      {
        "state": "SE",
        "billNumber": "sfs-2011-927",
        "billId": 9926
      },
      {
        "state": "SE",
        "billNumber": "sfs-2018-1463",
        "billId": 9918
      },
      {
        "state": "SK",
        "billNumber": "2015/373",
        "billId": 10050
      },
      {
        "state": "UK",
        "billNumber": "uksi/2017/1221",
        "billId": 9747
      },
      {
        "state": "EU",
        "billNumber": "32003D0082",
        "billId": 696
      },
      {
        "state": "EU",
        "billNumber": "32004D0312",
        "billId": 579
      },
      {
        "state": "EU",
        "billNumber": "32004D0486",
        "billId": 603
      },
      {
        "state": "EU",
        "billNumber": "32008L0033",
        "billId": 672
      },
      {
        "state": "EU",
        "billNumber": "32013R1257",
        "billId": 503
      },
      {
        "state": "EU",
        "billNumber": "32019D0665",
        "billId": 764
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000031056680",
        "billId": 9619
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000033691469",
        "billId": 9586
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047274648",
        "billId": 9473
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/149/made/en",
        "billId": 9947
      },
      {
        "state": "JP",
        "billNumber": "408M50000500001",
        "billId": 9499
      },
      {
        "state": "JP",
        "billNumber": "414M60001800001",
        "billId": 9547
      },
      {
        "state": "JP",
        "billNumber": "431M60001900001",
        "billId": 9560
      },
      {
        "state": "JP",
        "billNumber": "508AC0000000033",
        "billId": 9477
      },
      {
        "state": "NY",
        "billNumber": "A-2103",
        "billId": 3742
      },
      {
        "state": "NY",
        "billNumber": "A-2164",
        "billId": 3560
      },
      {
        "state": "NY",
        "billNumber": "S-2097",
        "billId": 3659
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/1403",
        "billId": 9981
      },
      {
        "state": "UK",
        "billNumber": "uksi/1997/648",
        "billId": 9764
      },
      {
        "state": "UK",
        "billNumber": "uksi/2005/263",
        "billId": 9755
      },
      {
        "state": "UK",
        "billNumber": "uksi/2013/1857",
        "billId": 9750
      },
      {
        "state": "UK",
        "billNumber": "wsi/2011/551",
        "billId": 9821
      },
      {
        "state": "EU",
        "billNumber": "32019D0638",
        "billId": 727
      },
      {
        "state": "EU",
        "billNumber": "32018L0850",
        "billId": 626
      },
      {
        "state": "EU",
        "billNumber": "32019D2193",
        "billId": 779
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000052450618",
        "billId": 9597
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-27",
        "billId": 9738
      },
      {
        "state": "NY",
        "billNumber": "S-1459",
        "billId": 1000
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000019906779",
        "billId": 9656
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-23",
        "billId": 9733
      },
      {
        "state": "SE",
        "billNumber": "sfs-2023-133",
        "billId": 9908
      },
      {
        "state": "CL",
        "billNumber": "1090894",
        "billId": 9900
      },
      {
        "state": "DC",
        "billNumber": "D.C. Law 24-320",
        "billId": 4798
      },
      {
        "state": "EU",
        "billNumber": "32008L0098",
        "billId": 7
      },
      {
        "state": "EU",
        "billNumber": "32024R1252",
        "billId": 859
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043327059",
        "billId": 9602
      },
      {
        "state": "JP",
        "billNumber": "407CO0000000411",
        "billId": 9483
      },
      {
        "state": "JP",
        "billNumber": "419M60001200005",
        "billId": 9555
      },
      {
        "state": "JP",
        "billNumber": "504M60001000001",
        "billId": 9564
      },
      {
        "state": "LT",
        "billNumber": "TAIS.325345",
        "billId": 10056
      },
      {
        "state": "NL",
        "billNumber": "BWBR0045640",
        "billId": 9863
      },
      {
        "state": "NY",
        "billNumber": "S-5663",
        "billId": 3778
      },
      {
        "state": "SE",
        "billNumber": "sfs-2000-208",
        "billId": 9938
      },
      {
        "state": "SE",
        "billNumber": "sfs-2007-186",
        "billId": 9933
      },
      {
        "state": "UK",
        "billNumber": "ssi/2002/147",
        "billId": 9759
      },
      {
        "state": "UK",
        "billNumber": "ssi/2009/247",
        "billId": 9785
      },
      {
        "state": "UK",
        "billNumber": "uksi/1999/1361",
        "billId": 9763
      },
      {
        "state": "UK",
        "billNumber": "uksi/2024/1332",
        "billId": 9740
      },
      {
        "state": "UK",
        "billNumber": "wsi/2002/813",
        "billId": 9757
      },
      {
        "state": "SE",
        "billNumber": "sfs-2005-220",
        "billId": 9935
      },
      {
        "state": "SC",
        "billNumber": "S-171",
        "billId": 997
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/1994/06/17/n4/jo/fr",
        "billId": 10040
      },
      {
        "state": "BR",
        "billNumber": "_ato2019-2022/2022/decreto/D10936.htm",
        "billId": 9958
      },
      {
        "state": "EU",
        "billNumber": "32009D0851",
        "billId": 641
      },
      {
        "state": "JP",
        "billNumber": "414CO0000000389",
        "billId": 9487
      },
      {
        "state": "JP",
        "billNumber": "507CO0000000003",
        "billId": 9491
      },
      {
        "state": "JP",
        "billNumber": "508M60001740001",
        "billId": 9580
      },
      {
        "state": "MA",
        "billNumber": "HD-4318",
        "billId": 4205
      },
      {
        "state": "NL",
        "billNumber": "BWBR0050381",
        "billId": 9861
      },
      {
        "state": "NY",
        "billNumber": "A-8195",
        "billId": 3857
      },
      {
        "state": "NY",
        "billNumber": "S-73",
        "billId": 4602
      },
      {
        "state": "OR",
        "billNumber": "HB-3220",
        "billId": 4669
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/779",
        "billId": 9978
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1587",
        "billId": 9969
      },
      {
        "state": "SE",
        "billNumber": "sfs-1998-902",
        "billId": 9940
      },
      {
        "state": "SE",
        "billNumber": "sfs-2014-1074",
        "billId": 9923
      },
      {
        "state": "UK",
        "billNumber": "nisr/2009/159",
        "billId": 9786
      },
      {
        "state": "UK",
        "billNumber": "ukpga/2021/30",
        "billId": 9739
      },
      {
        "state": "UK",
        "billNumber": "uksi/2002/732",
        "billId": 9758
      },
      {
        "state": "UK",
        "billNumber": "uksi/2018/1214",
        "billId": 9771
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000022740348",
        "billId": 9659
      },
      {
        "state": "EU",
        "billNumber": "32024R3230",
        "billId": 900
      },
      {
        "state": "JP",
        "billNumber": "425M60001000005",
        "billId": 9557
      },
      {
        "state": "EU",
        "billNumber": "32021D1384",
        "billId": 774
      },
      {
        "state": "NY",
        "billNumber": "A-4641",
        "billId": 2066
      },
      {
        "state": "NY",
        "billNumber": "S-7553",
        "billId": 2327
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/992",
        "billId": 9986
      },
      {
        "state": "PL",
        "billNumber": "DU/2022/699",
        "billId": 9974
      },
      {
        "state": "UK",
        "billNumber": "ukpga/2003/29",
        "billId": 9808
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/1648",
        "billId": 9977
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047439314",
        "billId": 9476
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000049889812",
        "billId": 9583
      },
      {
        "state": "EU",
        "billNumber": "32016D2323",
        "billId": 434
      },
      {
        "state": "UK",
        "billNumber": "ssi/2023/160",
        "billId": 9781
      },
      {
        "state": "CL",
        "billNumber": "1154847",
        "billId": 9901
      },
      {
        "state": "SE",
        "billNumber": "sfs-2025-813",
        "billId": 9910
      }
    ]
  },
  {
    "lever": "recycled_content",
    "name": "Recycled Content",
    "headline": "Incorporate post-consumer recycled content",
    "direction": "Incorporate minimum 25% recycled plastic content in PET beverage bottles.",
    "focus": [
      "Packaging",
      "Electronics",
      "Textiles",
      "Organics",
      "Batteries",
      "Hazardous materials",
      "Furniture"
    ],
    "billCount": 71,
    "states": [
      "AT",
      "BR",
      "DK",
      "EE",
      "ES",
      "EU",
      "FI",
      "FR",
      "JP",
      "LV",
      "MN",
      "NL",
      "NY",
      "OR",
      "PL",
      "SE",
      "SI",
      "UK"
    ],
    "evidence": {
      "state": "AT",
      "bill": "20008902",
      "quote": "From 2025: ensure PET beverage bottles (Annex 6 Point 3) contain on average at least 25% recycled plastic content (calculated per calendar year)"
    },
    "feeImpact": {
      "malus": true,
      "bonus": true,
      "setJurisdictions": [
        "ES",
        "EU",
        "FR",
        "JP",
        "LV"
      ],
      "usPending": true,
      "examples": []
    },
    "bills": [
      {
        "state": "AT",
        "billNumber": "20008902",
        "billId": 9953
      },
      {
        "state": "NY",
        "billNumber": "S-5027C",
        "billId": 1100
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1658",
        "billId": 9993
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/927",
        "billId": 9991
      },
      {
        "state": "SE",
        "billNumber": "sfs-2018-1462",
        "billId": 9919
      },
      {
        "state": "BR",
        "billNumber": "_ato2023-2026/2025/decreto/D12688.htm",
        "billId": 9960
      },
      {
        "state": "EU",
        "billNumber": "32008D0440",
        "billId": 442
      },
      {
        "state": "EU",
        "billNumber": "32025R0040",
        "billId": 1
      },
      {
        "state": "JP",
        "billNumber": "413M60000400059",
        "billId": 9517
      },
      {
        "state": "JP",
        "billNumber": "413M60000400078",
        "billId": 9509
      },
      {
        "state": "JP",
        "billNumber": "508M60000400007",
        "billId": 9571
      },
      {
        "state": "JP",
        "billNumber": "508M60000400008",
        "billId": 9573
      },
      {
        "state": "JP",
        "billNumber": "508M60000400009",
        "billId": 9572
      },
      {
        "state": "JP",
        "billNumber": "508M60000400010",
        "billId": 9576
      },
      {
        "state": "JP",
        "billNumber": "508M60000400011",
        "billId": 9574
      },
      {
        "state": "JP",
        "billNumber": "508M60000740002",
        "billId": 9578
      },
      {
        "state": "NL",
        "billNumber": "BWBR0018139",
        "billId": 9868
      },
      {
        "state": "OR",
        "billNumber": "HB-3780",
        "billId": 3692
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2022-5809",
        "billId": 9892
      },
      {
        "state": "MN",
        "billNumber": "HF-3911",
        "billId": 4980
      },
      {
        "state": "EU",
        "billNumber": "32009D0292",
        "billId": 684
      },
      {
        "state": "JP",
        "billNumber": "413M60000400082",
        "billId": 9524
      },
      {
        "state": "JP",
        "billNumber": "413M60000400083",
        "billId": 9522
      },
      {
        "state": "NL",
        "billNumber": "BWBR0048299",
        "billId": 9860
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2025-17186",
        "billId": 9897
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047483124",
        "billId": 9431
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-18",
        "billId": 9731
      },
      {
        "state": "EU",
        "billNumber": "32023D2683",
        "billId": 883
      },
      {
        "state": "EU",
        "billNumber": "32001D0171",
        "billId": 512
      },
      {
        "state": "JP",
        "billNumber": "413M60000400088",
        "billId": 9526
      },
      {
        "state": "EU",
        "billNumber": "32022R1616",
        "billId": 793
      },
      {
        "state": "EU",
        "billNumber": "32024L0232",
        "billId": 714
      },
      {
        "state": "EU",
        "billNumber": "32024R1781",
        "billId": 8
      },
      {
        "state": "FI",
        "billNumber": "2011/646",
        "billId": 10030
      },
      {
        "state": "JP",
        "billNumber": "403AC0000000048",
        "billId": 847
      },
      {
        "state": "JP",
        "billNumber": "413M60000400079",
        "billId": 9506
      },
      {
        "state": "JP",
        "billNumber": "413M60000400085",
        "billId": 9525
      },
      {
        "state": "JP",
        "billNumber": "413M60000400086",
        "billId": 9527
      },
      {
        "state": "JP",
        "billNumber": "413M60000400089",
        "billId": 9523
      },
      {
        "state": "JP",
        "billNumber": "413M60000400090",
        "billId": 9515
      },
      {
        "state": "JP",
        "billNumber": "413M60000400091",
        "billId": 9513
      },
      {
        "state": "JP",
        "billNumber": "506AC0000000041",
        "billId": 9478
      },
      {
        "state": "NL",
        "billNumber": "BWBR0013707",
        "billId": 9883
      },
      {
        "state": "NL",
        "billNumber": "BWBR0048093",
        "billId": 9858
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032847905",
        "billId": 9439
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-3",
        "billId": 9729
      },
      {
        "state": "NY",
        "billNumber": "S-5062",
        "billId": 3596
      },
      {
        "state": "EU",
        "billNumber": "32002D0525",
        "billId": 659
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000042592423",
        "billId": 9587
      },
      {
        "state": "EU",
        "billNumber": "32025R0351",
        "billId": 868
      },
      {
        "state": "JP",
        "billNumber": "413M60000400080",
        "billId": 9528
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2021-5868",
        "billId": 9896
      },
      {
        "state": "EU",
        "billNumber": "32025R2269",
        "billId": 914
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000049184670",
        "billId": 9441
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-12",
        "billId": 9727
      },
      {
        "state": "JP",
        "billNumber": "413M60000400087",
        "billId": 9521
      },
      {
        "state": "JP",
        "billNumber": "424AC0000000057",
        "billId": 845
      },
      {
        "state": "SI",
        "billNumber": "2021-01-1053",
        "billId": 10057
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043458675",
        "billId": 9440
      },
      {
        "state": "NY",
        "billNumber": "A-6193",
        "billId": 3105
      },
      {
        "state": "NY",
        "billNumber": "S-3217",
        "billId": 3115
      },
      {
        "state": "DK",
        "billNumber": "lta/2025/1146",
        "billId": 10024
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000110",
        "billId": 9480
      },
      {
        "state": "EU",
        "billNumber": "32025L1892",
        "billId": 841
      },
      {
        "state": "LV",
        "billNumber": "124707",
        "billId": 10047
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000052450618",
        "billId": 9597
      },
      {
        "state": "NL",
        "billNumber": "BWBR0046477",
        "billId": 9885
      },
      {
        "state": "UK",
        "billNumber": "uksi/2025/1369",
        "billId": 9744
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000104",
        "billId": 852
      },
      {
        "state": "EE",
        "billNumber": "749804",
        "billId": 10042
      },
      {
        "state": "EU",
        "billNumber": "32024R1252",
        "billId": 859
      }
    ]
  },
  {
    "lever": "source_reduction",
    "name": "Source Reduction",
    "headline": "Reduce packaging material per unit (lightweight, right-size)",
    "direction": "Minimize packaging volume and weight while maintaining safety and hygiene.",
    "focus": [
      "Packaging",
      "Electronics",
      "Organics",
      "Batteries",
      "Hazardous materials",
      "Textiles",
      "Biobased"
    ],
    "billCount": 138,
    "states": [
      "AT",
      "BR",
      "CA",
      "CH",
      "CL",
      "CZ",
      "DE",
      "DK",
      "EE",
      "ES",
      "EU",
      "FI",
      "FR",
      "JP",
      "LT",
      "LU",
      "LV",
      "MN",
      "NL",
      "NY",
      "OR",
      "PL",
      "SE",
      "SI",
      "UK",
      "WA"
    ],
    "evidence": {
      "state": "EE",
      "bill": "113032019103",
      "quote": "Packaging must be designed and manufactured to minimise volume and weight while meeting safety and hygiene requirements, and to enable reuse or recovery including recycling"
    },
    "feeImpact": {
      "malus": true,
      "bonus": true,
      "setJurisdictions": [
        "CH",
        "CL",
        "EE",
        "ES",
        "EU",
        "FR",
        "JP",
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
        "state": "EE",
        "billNumber": "113032019103",
        "billId": 10043
      },
      {
        "state": "EU",
        "billNumber": "32021R1929",
        "billId": 776
      },
      {
        "state": "EU",
        "billNumber": "32025R0040",
        "billId": 1
      },
      {
        "state": "FI",
        "billNumber": "2011/646",
        "billId": 10030
      },
      {
        "state": "FI",
        "billNumber": "2021/714",
        "billId": 10031
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043458675",
        "billId": 9440
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-11",
        "billId": 9717
      },
      {
        "state": "JP",
        "billNumber": "407AC0000000112",
        "billId": 848
      },
      {
        "state": "JP",
        "billNumber": "413M60000400062",
        "billId": 9533
      },
      {
        "state": "JP",
        "billNumber": "413M60000400063",
        "billId": 9531
      },
      {
        "state": "JP",
        "billNumber": "413M60000400064",
        "billId": 9537
      },
      {
        "state": "JP",
        "billNumber": "413M60000400065",
        "billId": 9534
      },
      {
        "state": "JP",
        "billNumber": "413M60000400066",
        "billId": 9536
      },
      {
        "state": "JP",
        "billNumber": "413M60000400067",
        "billId": 9530
      },
      {
        "state": "JP",
        "billNumber": "413M60000400068",
        "billId": 9535
      },
      {
        "state": "JP",
        "billNumber": "413M60000400069",
        "billId": 9532
      },
      {
        "state": "JP",
        "billNumber": "413M60000400070",
        "billId": 9511
      },
      {
        "state": "JP",
        "billNumber": "413M60000400071",
        "billId": 9503
      },
      {
        "state": "JP",
        "billNumber": "413M60000400072",
        "billId": 9507
      },
      {
        "state": "JP",
        "billNumber": "413M60000400073",
        "billId": 9505
      },
      {
        "state": "JP",
        "billNumber": "413M60000400074",
        "billId": 9512
      },
      {
        "state": "JP",
        "billNumber": "413M60000400075",
        "billId": 9508
      },
      {
        "state": "JP",
        "billNumber": "413M60000C00004",
        "billId": 9539
      },
      {
        "state": "JP",
        "billNumber": "504M60007FFE001",
        "billId": 9562
      },
      {
        "state": "LT",
        "billNumber": "TAIS.161216",
        "billId": 10054
      },
      {
        "state": "NL",
        "billNumber": "BWBR0018139",
        "billId": 9868
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/542",
        "billId": 9996
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/160",
        "billId": 9994
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/927",
        "billId": 9991
      },
      {
        "state": "SE",
        "billNumber": "sfs-2018-1462",
        "billId": 9919
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-18",
        "billId": 9731
      },
      {
        "state": "MN",
        "billNumber": "HF-3911",
        "billId": 4980
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2022-5809",
        "billId": 9892
      },
      {
        "state": "EU",
        "billNumber": "32018L0852",
        "billId": 627
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-17",
        "billId": 9724
      },
      {
        "state": "JP",
        "billNumber": "413M60000400088",
        "billId": 9526
      },
      {
        "state": "JP",
        "billNumber": "413M60000400090",
        "billId": 9515
      },
      {
        "state": "JP",
        "billNumber": "413M60000400091",
        "billId": 9513
      },
      {
        "state": "JP",
        "billNumber": "413M60001F40004",
        "billId": 9546
      },
      {
        "state": "JP",
        "billNumber": "418M60000740001",
        "billId": 9553
      },
      {
        "state": "NY",
        "billNumber": "S-5062",
        "billId": 3596
      },
      {
        "state": "PL",
        "billNumber": "DU/2013/888",
        "billId": 10000
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/150",
        "billId": 9997
      },
      {
        "state": "PL",
        "billNumber": "DU/2020/1114",
        "billId": 9995
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1658",
        "billId": 9993
      },
      {
        "state": "SE",
        "billNumber": "sfs-1997-185",
        "billId": 9945
      },
      {
        "state": "AT",
        "billNumber": "20008902",
        "billId": 9953
      },
      {
        "state": "NL",
        "billNumber": "BWBR0037392",
        "billId": 9866
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000044036494",
        "billId": 9624
      },
      {
        "state": "DE",
        "billNumber": "krwg",
        "billId": 9846
      },
      {
        "state": "DK",
        "billNumber": "lta/2019/1218",
        "billId": 10029
      },
      {
        "state": "EU",
        "billNumber": "31994L0062",
        "billId": 5
      },
      {
        "state": "JP",
        "billNumber": "413M60000400079",
        "billId": 9506
      },
      {
        "state": "SE",
        "billNumber": "sfs-1998-808",
        "billId": 9943
      },
      {
        "state": "CL",
        "billNumber": "1208163",
        "billId": 9904
      },
      {
        "state": "EU",
        "billNumber": "32015L0720",
        "billId": 489
      },
      {
        "state": "PL",
        "billNumber": "DU/2008/1464",
        "billId": 10010
      },
      {
        "state": "UK",
        "billNumber": "asc/2023/2",
        "billId": 9797
      },
      {
        "state": "DE",
        "billNumber": "ewkfondsg",
        "billId": 9848
      },
      {
        "state": "EE",
        "billNumber": "918053",
        "billId": 10044
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-3",
        "billId": 9729
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047483124",
        "billId": 9431
      },
      {
        "state": "SE",
        "billNumber": "sfs-2014-1073",
        "billId": 9924
      },
      {
        "state": "JP",
        "billNumber": "413M60000740001",
        "billId": 9541
      },
      {
        "state": "EU",
        "billNumber": "32023D2683",
        "billId": 883
      },
      {
        "state": "AT",
        "billNumber": "20002086",
        "billId": 9952
      },
      {
        "state": "BR",
        "billNumber": "_ato2007-2010/2010/lei/l12305.htm",
        "billId": 9957
      },
      {
        "state": "CZ",
        "billNumber": "2020/541",
        "billId": 10063
      },
      {
        "state": "EU",
        "billNumber": "32024R1781",
        "billId": 8
      },
      {
        "state": "JP",
        "billNumber": "403AC0000000048",
        "billId": 847
      },
      {
        "state": "JP",
        "billNumber": "407M50000100061",
        "billId": 9496
      },
      {
        "state": "JP",
        "billNumber": "504CO0000000025",
        "billId": 9490
      },
      {
        "state": "LT",
        "billNumber": "TAIS.59267",
        "billId": 10053
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/1994/06/17/n4/jo/fr",
        "billId": 10040
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/2017/03/21/a330/jo/fr",
        "billId": 10037
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/1895",
        "billId": 10005
      },
      {
        "state": "DE",
        "billNumber": "ewkfondsv",
        "billId": 9856
      },
      {
        "state": "EU",
        "billNumber": "32018D0896",
        "billId": 729
      },
      {
        "state": "EU",
        "billNumber": "32022D0162",
        "billId": 768
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000000645543",
        "billId": 9665
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000019906779",
        "billId": 9656
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-1002",
        "billId": 9914
      },
      {
        "state": "CL",
        "billNumber": "1157019",
        "billId": 9902
      },
      {
        "state": "JP",
        "billNumber": "408M50000500001",
        "billId": 9499
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2024-21709",
        "billId": 9899
      },
      {
        "state": "BR",
        "billNumber": "_ato2023-2026/2025/decreto/D12688.htm",
        "billId": 9960
      },
      {
        "state": "EU",
        "billNumber": "32004L0012",
        "billId": 533
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-12",
        "billId": 9727
      },
      {
        "state": "SI",
        "billNumber": "2015-01-1513",
        "billId": 10058
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000031056680",
        "billId": 9619
      },
      {
        "state": "EU",
        "billNumber": "32013R1257",
        "billId": 503
      },
      {
        "state": "JP",
        "billNumber": "503AC0000000060",
        "billId": 849
      },
      {
        "state": "EU",
        "billNumber": "31999D0042",
        "billId": 607
      },
      {
        "state": "JP",
        "billNumber": "345AC0000000137",
        "billId": 9479
      },
      {
        "state": "JP",
        "billNumber": "407CO0000000411",
        "billId": 9483
      },
      {
        "state": "JP",
        "billNumber": "413M60000400084",
        "billId": 9529
      },
      {
        "state": "JP",
        "billNumber": "418M60000740002",
        "billId": 9554
      },
      {
        "state": "JP",
        "billNumber": "504M60001000001",
        "billId": 9564
      },
      {
        "state": "LV",
        "billNumber": "57207",
        "billId": 10046
      },
      {
        "state": "UK",
        "billNumber": "nisr/2020/285",
        "billId": 9769
      },
      {
        "state": "EU",
        "billNumber": "32013L0002",
        "billId": 463
      },
      {
        "state": "CH",
        "billNumber": "cc/2001/359",
        "billId": 9966
      },
      {
        "state": "CL",
        "billNumber": "1090894",
        "billId": 9900
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032847905",
        "billId": 9439
      },
      {
        "state": "JP",
        "billNumber": "407M50000740001",
        "billId": 9498
      },
      {
        "state": "JP",
        "billNumber": "413CO0000000176",
        "billId": 9486
      },
      {
        "state": "UK",
        "billNumber": "uksi/2020/904",
        "billId": 9768
      },
      {
        "state": "UK",
        "billNumber": "nisr/2023/25",
        "billId": 9783
      },
      {
        "state": "UK",
        "billNumber": "asp/2024/13",
        "billId": 9765
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000022740348",
        "billId": 9659
      },
      {
        "state": "EU",
        "billNumber": "32008L0098",
        "billId": 7
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000033691469",
        "billId": 9586
      },
      {
        "state": "CL",
        "billNumber": "1223902",
        "billId": 9903
      },
      {
        "state": "SE",
        "billNumber": "sfs-1998-902",
        "billId": 9940
      },
      {
        "state": "UK",
        "billNumber": "ssi/2025/10",
        "billId": 9767
      },
      {
        "state": "LV",
        "billNumber": "221378",
        "billId": 10045
      },
      {
        "state": "CL",
        "billNumber": "1154847",
        "billId": 9901
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000116",
        "billId": 851
      },
      {
        "state": "EU",
        "billNumber": "32011D0677",
        "billId": 680
      },
      {
        "state": "JP",
        "billNumber": "419M60001200005",
        "billId": 9555
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/1403",
        "billId": 9981
      },
      {
        "state": "EU",
        "billNumber": "32025L1892",
        "billId": 841
      },
      {
        "state": "OR",
        "billNumber": "HB-3780",
        "billId": 3692
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-23",
        "billId": 9733
      },
      {
        "state": "BR",
        "billNumber": "_ato2019-2022/2022/decreto/D10936.htm",
        "billId": 9958
      },
      {
        "state": "CA",
        "billNumber": "AB-1857",
        "billId": 3418
      },
      {
        "state": "EU",
        "billNumber": "31999L0031",
        "billId": 451
      },
      {
        "state": "NL",
        "billNumber": "BWBR0050381",
        "billId": 9861
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/779",
        "billId": 9978
      },
      {
        "state": "EU",
        "billNumber": "31999D0652",
        "billId": 551
      },
      {
        "state": "EU",
        "billNumber": "32017D1508",
        "billId": 433
      },
      {
        "state": "NL",
        "billNumber": "BWBR0045640",
        "billId": 9863
      },
      {
        "state": "SE",
        "billNumber": "sfs-2016-1041",
        "billId": 9921
      },
      {
        "state": "UK",
        "billNumber": "uksi/2024/1332",
        "billId": 9740
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000029374870",
        "billId": 9651
      },
      {
        "state": "PL",
        "billNumber": "DU/2022/699",
        "billId": 9974
      },
      {
        "state": "WA",
        "billNumber": "SB-5284",
        "billId": 1080
      },
      {
        "state": "DK",
        "billNumber": "lta/2025/882",
        "billId": 10025
      }
    ]
  },
  {
    "lever": "reuse_refill",
    "name": "Reuse & Refill",
    "headline": "Shift to reusable / refillable formats",
    "direction": "Design pallet wrappings and straps for reuse; achieve 40% reuse target annually.",
    "focus": [
      "Packaging",
      "Textiles",
      "Electronics",
      "Batteries",
      "Organics",
      "Hazardous materials",
      "Furniture"
    ],
    "billCount": 86,
    "states": [
      "AT",
      "BR",
      "CH",
      "CL",
      "CZ",
      "DE",
      "DK",
      "EE",
      "ES",
      "EU",
      "FI",
      "FR",
      "IE",
      "JP",
      "LT",
      "MN",
      "NL",
      "NY",
      "PL",
      "SE",
      "SI",
      "UK",
      "VT"
    ],
    "evidence": {
      "state": "EU",
      "bill": "32026D0429",
      "quote": "Economic operators using pallet wrappings and straps are subject to the overall 40% re-use target under Article 29(1) of Regulation (EU) 2025/40 for transport packaging formats in a calendar year (not exempted by this Decision)"
    },
    "feeImpact": {
      "malus": true,
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
        "state": "EU",
        "billNumber": "32026D0429",
        "billId": 930
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000026863961",
        "billId": 9669
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032770063",
        "billId": 9668
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000053625694",
        "billId": 9457
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-22",
        "billId": 9734
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-24",
        "billId": 9735
      },
      {
        "state": "IE",
        "billNumber": "eli/2007/si/798/made/en",
        "billId": 9951
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/282/made/en",
        "billId": 9949
      },
      {
        "state": "NL",
        "billNumber": "BWBR0048093",
        "billId": 9858
      },
      {
        "state": "NL",
        "billNumber": "BWBR0048299",
        "billId": 9860
      },
      {
        "state": "CL",
        "billNumber": "1157019",
        "billId": 9902
      },
      {
        "state": "DE",
        "billNumber": "ewkfondsg",
        "billId": 9848
      },
      {
        "state": "JP",
        "billNumber": "418M60000740001",
        "billId": 9553
      },
      {
        "state": "DE",
        "billNumber": "battdg",
        "billId": 9845
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-3",
        "billId": 9729
      },
      {
        "state": "MN",
        "billNumber": "HF-3911",
        "billId": 4980
      },
      {
        "state": "AT",
        "billNumber": "20008902",
        "billId": 9953
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043458675",
        "billId": 9440
      },
      {
        "state": "EU",
        "billNumber": "32018L0852",
        "billId": 627
      },
      {
        "state": "EU",
        "billNumber": "32024R1781",
        "billId": 8
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000050749111",
        "billId": 9466
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/927",
        "billId": 9991
      },
      {
        "state": "SE",
        "billNumber": "sfs-2014-1073",
        "billId": 9924
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-999",
        "billId": 9911
      },
      {
        "state": "UK",
        "billNumber": "uksi/1999/3447",
        "billId": 9762
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2025-17186",
        "billId": 9897
      },
      {
        "state": "NL",
        "billNumber": "BWBR0044197",
        "billId": 9859
      },
      {
        "state": "CH",
        "billNumber": "cc/2000/299",
        "billId": 9965
      },
      {
        "state": "EU",
        "billNumber": "32025R0040",
        "billId": 1
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-17",
        "billId": 9724
      },
      {
        "state": "JP",
        "billNumber": "407AC0000000112",
        "billId": 848
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1852",
        "billId": 9992
      },
      {
        "state": "SE",
        "billNumber": "sfs-2006-1273",
        "billId": 9934
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2024-21709",
        "billId": 9899
      },
      {
        "state": "VT",
        "billNumber": "H-67",
        "billId": 4988
      },
      {
        "state": "EU",
        "billNumber": "32012L0019",
        "billId": 2
      },
      {
        "state": "BR",
        "billNumber": "_ato2023-2026/2025/decreto/D12688.htm",
        "billId": 9960
      },
      {
        "state": "DK",
        "billNumber": "lta/2025/1146",
        "billId": 10024
      },
      {
        "state": "EE",
        "billNumber": "113032019103",
        "billId": 10043
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-18",
        "billId": 9731
      },
      {
        "state": "JP",
        "billNumber": "403AC0000000048",
        "billId": 847
      },
      {
        "state": "PL",
        "billNumber": "DU/2013/888",
        "billId": 10000
      },
      {
        "state": "SE",
        "billNumber": "sfs-1997-185",
        "billId": 9945
      },
      {
        "state": "FI",
        "billNumber": "2021/1029",
        "billId": 10034
      },
      {
        "state": "AT",
        "billNumber": "20002086",
        "billId": 9952
      },
      {
        "state": "EU",
        "billNumber": "32001D0524",
        "billId": 491
      },
      {
        "state": "EU",
        "billNumber": "32019D0665",
        "billId": 764
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10",
        "billId": 9725
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-11",
        "billId": 9717
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-5",
        "billId": 9728
      },
      {
        "state": "LT",
        "billNumber": "TAIS.161216",
        "billId": 10054
      },
      {
        "state": "NL",
        "billNumber": "BWBR0046477",
        "billId": 9885
      },
      {
        "state": "NY",
        "billNumber": "S-7552",
        "billId": 3378
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/1911",
        "billId": 9990
      },
      {
        "state": "UK",
        "billNumber": "nisr/2023/106",
        "billId": 9782
      },
      {
        "state": "EU",
        "billNumber": "31999D0823",
        "billId": 431
      },
      {
        "state": "EU",
        "billNumber": "32005D0270",
        "billId": 546
      },
      {
        "state": "EU",
        "billNumber": "31994L0062",
        "billId": 5
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-1001",
        "billId": 9915
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/2151",
        "billId": 9975
      },
      {
        "state": "EU",
        "billNumber": "31999D0042",
        "billId": 607
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000049184670",
        "billId": 9441
      },
      {
        "state": "EU",
        "billNumber": "32013L0002",
        "billId": 463
      },
      {
        "state": "JP",
        "billNumber": "407M50000740001",
        "billId": 9498
      },
      {
        "state": "UK",
        "billNumber": "uksi/2024/1332",
        "billId": 9740
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000041553759",
        "billId": 9463
      },
      {
        "state": "CZ",
        "billNumber": "2020/541",
        "billId": 10063
      },
      {
        "state": "UK",
        "billNumber": "nisr/2020/285",
        "billId": 9769
      },
      {
        "state": "BR",
        "billNumber": "_ato2007-2010/2010/lei/l12305.htm",
        "billId": 9957
      },
      {
        "state": "DE",
        "billNumber": "krwg",
        "billId": 9846
      },
      {
        "state": "EU",
        "billNumber": "32004L0012",
        "billId": 533
      },
      {
        "state": "NL",
        "billNumber": "BWBR0045640",
        "billId": 9863
      },
      {
        "state": "NY",
        "billNumber": "S-3217",
        "billId": 3115
      },
      {
        "state": "UK",
        "billNumber": "nisr/2023/25",
        "billId": 9783
      },
      {
        "state": "SI",
        "billNumber": "2021-01-1053",
        "billId": 10057
      },
      {
        "state": "EU",
        "billNumber": "32018L0851",
        "billId": 449
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000042575740",
        "billId": 9430
      },
      {
        "state": "UK",
        "billNumber": "uksi/2020/904",
        "billId": 9768
      },
      {
        "state": "EU",
        "billNumber": "32008L0098",
        "billId": 7
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/160",
        "billId": 9994
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-27",
        "billId": 9738
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047274648",
        "billId": 9473
      },
      {
        "state": "EU",
        "billNumber": "32023R0595",
        "billId": 838
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/779",
        "billId": 9978
      },
      {
        "state": "PL",
        "billNumber": "DU/2022/699",
        "billId": 9974
      },
      {
        "state": "UK",
        "billNumber": "ssi/2023/160",
        "billId": 9781
      }
    ]
  },
  {
    "lever": "toxics_elimination",
    "name": "Toxics Elimination",
    "headline": "Eliminate restricted substances (PFAS, heavy metals, etc.)",
    "direction": "Ensure batteries contain ≤0.0005 wt% mercury regardless of form.",
    "focus": [
      "Packaging",
      "Electronics",
      "Hazardous materials",
      "Batteries",
      "Vehicles",
      "Organics",
      "Textiles"
    ],
    "billCount": 201,
    "states": [
      "AT",
      "BR",
      "CH",
      "CL",
      "CZ",
      "DE",
      "DK",
      "EE",
      "ES",
      "EU",
      "FI",
      "FR",
      "IE",
      "JP",
      "LT",
      "LU",
      "LV",
      "ME",
      "MN",
      "NL",
      "NY",
      "OR",
      "PL",
      "SE",
      "SI",
      "SK",
      "UK",
      "VT",
      "WA"
    ],
    "evidence": {
      "state": "AT",
      "bill": "20005815",
      "quote": "do not place on market batteries containing more than 0.0005 wt% mercury (regardless of whether built into devices)"
    },
    "feeImpact": {
      "malus": true,
      "bonus": true,
      "setJurisdictions": [
        "ES",
        "EU",
        "FR",
        "NL"
      ],
      "usPending": true,
      "examples": []
    },
    "bills": [
      {
        "state": "AT",
        "billNumber": "20005815",
        "billId": 9955
      },
      {
        "state": "EU",
        "billNumber": "32011L0065",
        "billId": 510
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2008-2387",
        "billId": 9895
      },
      {
        "state": "NL",
        "billNumber": "BWBR0024492",
        "billId": 9876
      },
      {
        "state": "EU",
        "billNumber": "32009L0001",
        "billId": 541
      },
      {
        "state": "JP",
        "billNumber": "413M60000400086",
        "billId": 9527
      },
      {
        "state": "NL",
        "billNumber": "BWBR0018139",
        "billId": 9868
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/542",
        "billId": 9996
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/927",
        "billId": 9991
      },
      {
        "state": "EU",
        "billNumber": "32006L0066",
        "billId": 504
      },
      {
        "state": "EU",
        "billNumber": "32009R0767",
        "billId": 611
      },
      {
        "state": "NY",
        "billNumber": "S-5027C",
        "billId": 1100
      },
      {
        "state": "AT",
        "billNumber": "20008902",
        "billId": 9953
      },
      {
        "state": "JP",
        "billNumber": "413M60000400083",
        "billId": 9522
      },
      {
        "state": "CL",
        "billNumber": "1223902",
        "billId": 9903
      },
      {
        "state": "DE",
        "billNumber": "altholzv",
        "billId": 9852
      },
      {
        "state": "DK",
        "billNumber": "lta/2025/1146",
        "billId": 10024
      },
      {
        "state": "EE",
        "billNumber": "113032019103",
        "billId": 10043
      },
      {
        "state": "EE",
        "billNumber": "749804",
        "billId": 10042
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2006-9832",
        "billId": 9898
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2021-5868",
        "billId": 9896
      },
      {
        "state": "EU",
        "billNumber": "31994L0062",
        "billId": 5
      },
      {
        "state": "EU",
        "billNumber": "32001D0171",
        "billId": 512
      },
      {
        "state": "EU",
        "billNumber": "32001D0753",
        "billId": 608
      },
      {
        "state": "EU",
        "billNumber": "32009D0292",
        "billId": 684
      },
      {
        "state": "EU",
        "billNumber": "32014L0072",
        "billId": 520
      },
      {
        "state": "EU",
        "billNumber": "32017L2102",
        "billId": 712
      },
      {
        "state": "EU",
        "billNumber": "32018L0849",
        "billId": 666
      },
      {
        "state": "EU",
        "billNumber": "32020L0360",
        "billId": 702
      },
      {
        "state": "EU",
        "billNumber": "32020L0362",
        "billId": 524
      },
      {
        "state": "EU",
        "billNumber": "32020L0364",
        "billId": 704
      },
      {
        "state": "EU",
        "billNumber": "32020L0365",
        "billId": 705
      },
      {
        "state": "EU",
        "billNumber": "32022R1616",
        "billId": 793
      },
      {
        "state": "EU",
        "billNumber": "32023L0544",
        "billId": 664
      },
      {
        "state": "EU",
        "billNumber": "32024L0232",
        "billId": 714
      },
      {
        "state": "EU",
        "billNumber": "32025R0351",
        "billId": 868
      },
      {
        "state": "FI",
        "billNumber": "2011/646",
        "billId": 10030
      },
      {
        "state": "FI",
        "billNumber": "2014/520",
        "billId": 10033
      },
      {
        "state": "FI",
        "billNumber": "2021/1029",
        "billId": 10034
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000044155771",
        "billId": 9605
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/281/made/en",
        "billId": 9950
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/283/made/en",
        "billId": 9948
      },
      {
        "state": "JP",
        "billNumber": "410CO0000000378",
        "billId": 9484
      },
      {
        "state": "JP",
        "billNumber": "413M60000400085",
        "billId": 9525
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/2017/03/21/a330/jo/fr",
        "billId": 10037
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/rgd/2018/07/02/a562/jo/fr",
        "billId": 10041
      },
      {
        "state": "LV",
        "billNumber": "57207",
        "billId": 10046
      },
      {
        "state": "NL",
        "billNumber": "BWBR0032405",
        "billId": 9871
      },
      {
        "state": "PL",
        "billNumber": "DU/2009/666",
        "billId": 10023
      },
      {
        "state": "PL",
        "billNumber": "DU/2013/888",
        "billId": 10000
      },
      {
        "state": "PL",
        "billNumber": "DU/2014/1322",
        "billId": 10022
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/150",
        "billId": 9997
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/521",
        "billId": 10017
      },
      {
        "state": "PL",
        "billNumber": "DU/2020/1114",
        "billId": 9995
      },
      {
        "state": "PL",
        "billNumber": "DU/2022/1113",
        "billId": 10013
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/160",
        "billId": 9994
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1658",
        "billId": 9993
      },
      {
        "state": "SE",
        "billNumber": "sfs-1998-808",
        "billId": 9943
      },
      {
        "state": "SI",
        "billNumber": "2010-01-0111",
        "billId": 10059
      },
      {
        "state": "SI",
        "billNumber": "2021-01-1053",
        "billId": 10057
      },
      {
        "state": "UK",
        "billNumber": "uksi/2003/2635",
        "billId": 9743
      },
      {
        "state": "UK",
        "billNumber": "uksi/2010/1094",
        "billId": 9796
      },
      {
        "state": "VT",
        "billNumber": "H-67",
        "billId": 4988
      },
      {
        "state": "ME",
        "billNumber": "LD-474",
        "billId": 1081
      },
      {
        "state": "WA",
        "billNumber": "SB-5144",
        "billId": 993
      },
      {
        "state": "DE",
        "billNumber": "altautov",
        "billId": 9847
      },
      {
        "state": "EU",
        "billNumber": "32000L0053",
        "billId": 6
      },
      {
        "state": "EU",
        "billNumber": "32002D0525",
        "billId": 659
      },
      {
        "state": "EU",
        "billNumber": "32005D0438",
        "billId": 550
      },
      {
        "state": "EU",
        "billNumber": "32020L0361",
        "billId": 703
      },
      {
        "state": "EU",
        "billNumber": "32020L0363",
        "billId": 525
      },
      {
        "state": "NL",
        "billNumber": "BWBR0007227",
        "billId": 9873
      },
      {
        "state": "NL",
        "billNumber": "BWBR0013707",
        "billId": 9883
      },
      {
        "state": "NL",
        "billNumber": "BWBR0016990",
        "billId": 9869
      },
      {
        "state": "UK",
        "billNumber": "nisr/1995/122",
        "billId": 9794
      },
      {
        "state": "UK",
        "billNumber": "nisr/2002/300",
        "billId": 9791
      },
      {
        "state": "UK",
        "billNumber": "uksi/1994/232",
        "billId": 9795
      },
      {
        "state": "UK",
        "billNumber": "uksi/2000/3097",
        "billId": 9793
      },
      {
        "state": "UK",
        "billNumber": "uksi/2015/63",
        "billId": 9788
      },
      {
        "state": "DE",
        "billNumber": "battdg",
        "billId": 9845
      },
      {
        "state": "MN",
        "billNumber": "HF-3911",
        "billId": 4980
      },
      {
        "state": "JP",
        "billNumber": "413M60000400082",
        "billId": 9524
      },
      {
        "state": "JP",
        "billNumber": "413M60000400084",
        "billId": 9529
      },
      {
        "state": "DE",
        "billNumber": "elektrog_2015",
        "billId": 9843
      },
      {
        "state": "EU",
        "billNumber": "32024R1781",
        "billId": 8
      },
      {
        "state": "JP",
        "billNumber": "413M60000400070",
        "billId": 9511
      },
      {
        "state": "JP",
        "billNumber": "413M60000400063",
        "billId": 9531
      },
      {
        "state": "JP",
        "billNumber": "413M60000400066",
        "billId": 9536
      },
      {
        "state": "JP",
        "billNumber": "413M60000400068",
        "billId": 9535
      },
      {
        "state": "NL",
        "billNumber": "BWBR0024500",
        "billId": 9875
      },
      {
        "state": "PL",
        "billNumber": "DU/2015/687",
        "billId": 10021
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047483124",
        "billId": 9431
      },
      {
        "state": "NL",
        "billNumber": "BWBR0044197",
        "billId": 9859
      },
      {
        "state": "EU",
        "billNumber": "32025R0040",
        "billId": 1
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000041553759",
        "billId": 9463
      },
      {
        "state": "JP",
        "billNumber": "413M60000400062",
        "billId": 9533
      },
      {
        "state": "JP",
        "billNumber": "413M60000400064",
        "billId": 9537
      },
      {
        "state": "JP",
        "billNumber": "413M60000400065",
        "billId": 9534
      },
      {
        "state": "JP",
        "billNumber": "413M60000400067",
        "billId": 9530
      },
      {
        "state": "JP",
        "billNumber": "413M60000400069",
        "billId": 9532
      },
      {
        "state": "JP",
        "billNumber": "413M60000400075",
        "billId": 9508
      },
      {
        "state": "JP",
        "billNumber": "413M60000400078",
        "billId": 9509
      },
      {
        "state": "JP",
        "billNumber": "413M60000C00004",
        "billId": 9539
      },
      {
        "state": "JP",
        "billNumber": "504M60007FFE001",
        "billId": 9562
      },
      {
        "state": "LT",
        "billNumber": "TAIS.161216",
        "billId": 10054
      },
      {
        "state": "OR",
        "billNumber": "HB-3780",
        "billId": 3692
      },
      {
        "state": "SE",
        "billNumber": "sfs-2018-1462",
        "billId": 9919
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-1000",
        "billId": 9916
      },
      {
        "state": "SE",
        "billNumber": "sfs-2008-834",
        "billId": 9930
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-3",
        "billId": 9729
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2025-17186",
        "billId": 9897
      },
      {
        "state": "CH",
        "billNumber": "cc/2021/633",
        "billId": 9962
      },
      {
        "state": "JP",
        "billNumber": "413M60000C00001",
        "billId": 9538
      },
      {
        "state": "JP",
        "billNumber": "425M60001400003",
        "billId": 9558
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000044036494",
        "billId": 9624
      },
      {
        "state": "NL",
        "billNumber": "BWBR0048299",
        "billId": 9860
      },
      {
        "state": "NY",
        "billNumber": "S-5062",
        "billId": 3596
      },
      {
        "state": "DK",
        "billNumber": "lta/2014/130",
        "billId": 10026
      },
      {
        "state": "EU",
        "billNumber": "32008L0033",
        "billId": 672
      },
      {
        "state": "EU",
        "billNumber": "32012R1179",
        "billId": 646
      },
      {
        "state": "EU",
        "billNumber": "32013R1257",
        "billId": 503
      },
      {
        "state": "EU",
        "billNumber": "32017R0997",
        "billId": 619
      },
      {
        "state": "EU",
        "billNumber": "32024R3229",
        "billId": 901
      },
      {
        "state": "EU",
        "billNumber": "32024R3230",
        "billId": 900
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000046664100",
        "billId": 9454
      },
      {
        "state": "JP",
        "billNumber": "413M60000400079",
        "billId": 9506
      },
      {
        "state": "JP",
        "billNumber": "413M60000400080",
        "billId": 9528
      },
      {
        "state": "JP",
        "billNumber": "413M60000400092",
        "billId": 9514
      },
      {
        "state": "JP",
        "billNumber": "414M60001400007",
        "billId": 9548
      },
      {
        "state": "JP",
        "billNumber": "508M60001400002",
        "billId": 9569
      },
      {
        "state": "JP",
        "billNumber": "508M60001440001",
        "billId": 9570
      },
      {
        "state": "PL",
        "billNumber": "DU/2013/1155",
        "billId": 10009
      },
      {
        "state": "SE",
        "billNumber": "sfs-2007-185",
        "billId": 9932
      },
      {
        "state": "SE",
        "billNumber": "sfs-2011-927",
        "billId": 9926
      },
      {
        "state": "SE",
        "billNumber": "sfs-2014-1073",
        "billId": 9924
      },
      {
        "state": "SI",
        "billNumber": "2024-01-2498",
        "billId": 10060
      },
      {
        "state": "EU",
        "billNumber": "32006D0340",
        "billId": 628
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000110",
        "billId": 9480
      },
      {
        "state": "PL",
        "billNumber": "DU/2015/1688",
        "billId": 10008
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000031056680",
        "billId": 9619
      },
      {
        "state": "BR",
        "billNumber": "_ato2007-2010/2010/lei/l12305.htm",
        "billId": 9957
      },
      {
        "state": "CL",
        "billNumber": "1090894",
        "billId": 9900
      },
      {
        "state": "CZ",
        "billNumber": "2020/541",
        "billId": 10063
      },
      {
        "state": "DE",
        "billNumber": "krwg",
        "billId": 9846
      },
      {
        "state": "EU",
        "billNumber": "32001D0524",
        "billId": 491
      },
      {
        "state": "EU",
        "billNumber": "32025R2269",
        "billId": 914
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10",
        "billId": 9725
      },
      {
        "state": "IE",
        "billNumber": "eli/2007/si/798/made/en",
        "billId": 9951
      },
      {
        "state": "JP",
        "billNumber": "414M60001800001",
        "billId": 9547
      },
      {
        "state": "JP",
        "billNumber": "504M60001400001",
        "billId": 9565
      },
      {
        "state": "LV",
        "billNumber": "221378",
        "billId": 10045
      },
      {
        "state": "BR",
        "billNumber": "_ato2023-2026/2023/decreto/D11413.htm",
        "billId": 9959
      },
      {
        "state": "DK",
        "billNumber": "lta/2019/1337",
        "billId": 10028
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000052450618",
        "billId": 9597
      },
      {
        "state": "LT",
        "billNumber": "TAIS.59267",
        "billId": 10053
      },
      {
        "state": "EU",
        "billNumber": "32014D0955",
        "billId": 652
      },
      {
        "state": "EU",
        "billNumber": "32025R1561",
        "billId": 844
      },
      {
        "state": "JP",
        "billNumber": "413M60001400001",
        "billId": 9540
      },
      {
        "state": "JP",
        "billNumber": "413M60001500001",
        "billId": 9502
      },
      {
        "state": "JP",
        "billNumber": "508M60001400003",
        "billId": 9568
      },
      {
        "state": "LT",
        "billNumber": "TAIS.325345",
        "billId": 10056
      },
      {
        "state": "PL",
        "billNumber": "DU/2017/2422",
        "billId": 9988
      },
      {
        "state": "SE",
        "billNumber": "sfs-1997-788",
        "billId": 9944
      },
      {
        "state": "SE",
        "billNumber": "sfs-2001-1063",
        "billId": 9937
      },
      {
        "state": "SI",
        "billNumber": "2015-01-1513",
        "billId": 10058
      },
      {
        "state": "LV",
        "billNumber": "267716",
        "billId": 10048
      },
      {
        "state": "UK",
        "billNumber": "nisr/2006/519",
        "billId": 9778
      },
      {
        "state": "EU",
        "billNumber": "32009D0851",
        "billId": 641
      },
      {
        "state": "EU",
        "billNumber": "32019D0638",
        "billId": 727
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-26",
        "billId": 9737
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/149/made/en",
        "billId": 9947
      },
      {
        "state": "JP",
        "billNumber": "414CO0000000389",
        "billId": 9487
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/1994/06/17/n4/jo/fr",
        "billId": 10040
      },
      {
        "state": "EU",
        "billNumber": "32025R0606",
        "billId": 913
      },
      {
        "state": "EU",
        "billNumber": "32004L0012",
        "billId": 533
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000029387124",
        "billId": 9635
      },
      {
        "state": "PL",
        "billNumber": "DU/2017/2056",
        "billId": 9998
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1587",
        "billId": 9969
      },
      {
        "state": "SK",
        "billNumber": "2015/373",
        "billId": 10050
      },
      {
        "state": "LV",
        "billNumber": "124707",
        "billId": 10047
      },
      {
        "state": "SE",
        "billNumber": "sfs-2007-193",
        "billId": 9931
      },
      {
        "state": "UK",
        "billNumber": "uksi/2015/1935",
        "billId": 9784
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000033691469",
        "billId": 9586
      },
      {
        "state": "DK",
        "billNumber": "lta/2015/1453",
        "billId": 10027
      },
      {
        "state": "EU",
        "billNumber": "32001D0118",
        "billId": 695
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043327059",
        "billId": 9602
      },
      {
        "state": "NY",
        "billNumber": "S-1459",
        "billId": 1000
      },
      {
        "state": "EU",
        "billNumber": "32004D0249",
        "billId": 556
      },
      {
        "state": "NY",
        "billNumber": "A-2164",
        "billId": 3560
      },
      {
        "state": "UK",
        "billNumber": "uksi/2001/2551",
        "billId": 9792
      },
      {
        "state": "EU",
        "billNumber": "32008L0098",
        "billId": 7
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/21",
        "billId": 9987
      },
      {
        "state": "UK",
        "billNumber": "ssi/2009/247",
        "billId": 9785
      },
      {
        "state": "BR",
        "billNumber": "_ato2019-2022/2022/decreto/D10936.htm",
        "billId": 9958
      },
      {
        "state": "UK",
        "billNumber": "uksi/2018/1214",
        "billId": 9771
      },
      {
        "state": "SE",
        "billNumber": "sfs-1998-902",
        "billId": 9940
      },
      {
        "state": "UK",
        "billNumber": "nisr/2009/159",
        "billId": 9786
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/992",
        "billId": 9986
      },
      {
        "state": "EU",
        "billNumber": "32016D2323",
        "billId": 434
      },
      {
        "state": "NL",
        "billNumber": "BWBR0024491",
        "billId": 9874
      },
      {
        "state": "SE",
        "billNumber": "sfs-2025-813",
        "billId": 9910
      }
    ]
  },
  {
    "lever": "material_restriction",
    "name": "Material Restrictions",
    "headline": "Avoid banned / restricted materials and formats",
    "direction": "Do not manufacture beverage containers or cups from expanded polystyrene.",
    "focus": [
      "Packaging",
      "Organics",
      "Electronics",
      "Textiles",
      "Hazardous materials",
      "Batteries",
      "Biobased"
    ],
    "billCount": 98,
    "states": [
      "AT",
      "CA",
      "CH",
      "CL",
      "DE",
      "DK",
      "EE",
      "ES",
      "EU",
      "FI",
      "FR",
      "IE",
      "JP",
      "LU",
      "LV",
      "MN",
      "NL",
      "PL",
      "SE",
      "SI",
      "UK",
      "WA"
    ],
    "evidence": {
      "state": "UK",
      "bill": "ssi/2021/410",
      "quote": "Do not manufacture single-use expanded polystyrene beverage containers, beverage cups, or food containers using expanded polystyrene."
    },
    "feeImpact": {
      "malus": true,
      "bonus": false,
      "setJurisdictions": [
        "CH",
        "EE",
        "EU",
        "FR",
        "LV",
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
        "state": "UK",
        "billNumber": "ssi/2021/410",
        "billId": 9801
      },
      {
        "state": "DE",
        "billNumber": "ewkverbotsv",
        "billId": 9849
      },
      {
        "state": "IE",
        "billNumber": "eli/2024/si/33/made/en",
        "billId": 9946
      },
      {
        "state": "SE",
        "billNumber": "sfs-2018-1462",
        "billId": 9919
      },
      {
        "state": "UK",
        "billNumber": "ssi/2025/188",
        "billId": 9803
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1658",
        "billId": 9993
      },
      {
        "state": "AT",
        "billNumber": "20002086",
        "billId": 9952
      },
      {
        "state": "EU",
        "billNumber": "32008D0440",
        "billId": 442
      },
      {
        "state": "EU",
        "billNumber": "32015L0720",
        "billId": 489
      },
      {
        "state": "EU",
        "billNumber": "32022D0162",
        "billId": 768
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000042753962",
        "billId": 9455
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000053625694",
        "billId": 9457
      },
      {
        "state": "JP",
        "billNumber": "418M60000740001",
        "billId": 9553
      },
      {
        "state": "JP",
        "billNumber": "420M60000600001",
        "billId": 9556
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/2017/03/21/a330/jo/fr",
        "billId": 10037
      },
      {
        "state": "LV",
        "billNumber": "57207",
        "billId": 10046
      },
      {
        "state": "NL",
        "billNumber": "BWBR0037392",
        "billId": 9866
      },
      {
        "state": "PL",
        "billNumber": "DU/2017/2056",
        "billId": 9998
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-1000",
        "billId": 9916
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-1002",
        "billId": 9914
      },
      {
        "state": "SI",
        "billNumber": "2021-01-2724",
        "billId": 10061
      },
      {
        "state": "UK",
        "billNumber": "asc/2023/2",
        "billId": 9797
      },
      {
        "state": "UK",
        "billNumber": "wsi/2023/1149",
        "billId": 9800
      },
      {
        "state": "UK",
        "billNumber": "wsi/2023/1288",
        "billId": 9799
      },
      {
        "state": "UK",
        "billNumber": "wsi/2025/716",
        "billId": 9798
      },
      {
        "state": "WA",
        "billNumber": "SB-5284",
        "billId": 1080
      },
      {
        "state": "DE",
        "billNumber": "ewkfondsg",
        "billId": 9848
      },
      {
        "state": "MN",
        "billNumber": "HF-1371",
        "billId": 1592
      },
      {
        "state": "MN",
        "billNumber": "SF-2619",
        "billId": 3919
      },
      {
        "state": "SE",
        "billNumber": "sfs-2016-1041",
        "billId": 9921
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-999",
        "billId": 9911
      },
      {
        "state": "AT",
        "billNumber": "20008902",
        "billId": 9953
      },
      {
        "state": "EU",
        "billNumber": "32021R1929",
        "billId": 776
      },
      {
        "state": "EU",
        "billNumber": "32023D1060",
        "billId": 874
      },
      {
        "state": "UK",
        "billNumber": "ssi/2020/154",
        "billId": 9807
      },
      {
        "state": "UK",
        "billNumber": "ssi/2025/189",
        "billId": 9802
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2022-5809",
        "billId": 9892
      },
      {
        "state": "EU",
        "billNumber": "32009R0767",
        "billId": 611
      },
      {
        "state": "EE",
        "billNumber": "113032019103",
        "billId": 10043
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000046285336",
        "billId": 9584
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/542",
        "billId": 9996
      },
      {
        "state": "UK",
        "billNumber": "uksi/2020/904",
        "billId": 9768
      },
      {
        "state": "SE",
        "billNumber": "sfs-2005-220",
        "billId": 9935
      },
      {
        "state": "DK",
        "billNumber": "lta/2025/1146",
        "billId": 10024
      },
      {
        "state": "CA",
        "billNumber": "SB-279",
        "billId": 4120
      },
      {
        "state": "JP",
        "billNumber": "504CO0000000025",
        "billId": 9490
      },
      {
        "state": "NL",
        "billNumber": "BWBR0046477",
        "billId": 9885
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/1911",
        "billId": 9990
      },
      {
        "state": "EU",
        "billNumber": "32025R0351",
        "billId": 868
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000025423069",
        "billId": 9667
      },
      {
        "state": "JP",
        "billNumber": "410CO0000000378",
        "billId": 9484
      },
      {
        "state": "JP",
        "billNumber": "413M60001500001",
        "billId": 9502
      },
      {
        "state": "EU",
        "billNumber": "32012R1179",
        "billId": 646
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043799891",
        "billId": 9615
      },
      {
        "state": "CH",
        "billNumber": "cc/2000/299",
        "billId": 9965
      },
      {
        "state": "LV",
        "billNumber": "124707",
        "billId": 10047
      },
      {
        "state": "SI",
        "billNumber": "2021-01-1053",
        "billId": 10057
      },
      {
        "state": "JP",
        "billNumber": "407M50000100061",
        "billId": 9496
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/150",
        "billId": 9997
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2024-21709",
        "billId": 9899
      },
      {
        "state": "SE",
        "billNumber": "sfs-2007-185",
        "billId": 9932
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043458675",
        "billId": 9440
      },
      {
        "state": "EE",
        "billNumber": "918053",
        "billId": 10044
      },
      {
        "state": "PL",
        "billNumber": "DU/2020/1114",
        "billId": 9995
      },
      {
        "state": "EU",
        "billNumber": "32023D2106",
        "billId": 865
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032610837",
        "billId": 9468
      },
      {
        "state": "JP",
        "billNumber": "504M60001000001",
        "billId": 9564
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1587",
        "billId": 9969
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/160",
        "billId": 9994
      },
      {
        "state": "CL",
        "billNumber": "1208163",
        "billId": 9904
      },
      {
        "state": "EU",
        "billNumber": "32022R1616",
        "billId": 793
      },
      {
        "state": "JP",
        "billNumber": "413M60000740001",
        "billId": 9541
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000041553759",
        "billId": 9463
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-18",
        "billId": 9731
      },
      {
        "state": "PL",
        "billNumber": "DU/2016/1863",
        "billId": 9999
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-1001",
        "billId": 9915
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032187830",
        "billId": 9636
      },
      {
        "state": "EU",
        "billNumber": "32025R0040",
        "billId": 1
      },
      {
        "state": "UK",
        "billNumber": "nisr/2020/285",
        "billId": 9769
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000049184670",
        "billId": 9441
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-1",
        "billId": 9721
      },
      {
        "state": "UK",
        "billNumber": "ssi/2025/10",
        "billId": 9767
      },
      {
        "state": "JP",
        "billNumber": "504M60001400001",
        "billId": 9565
      },
      {
        "state": "FI",
        "billNumber": "2021/1029",
        "billId": 10034
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-3",
        "billId": 9729
      },
      {
        "state": "EU",
        "billNumber": "32021D1752",
        "billId": 773
      },
      {
        "state": "JP",
        "billNumber": "507CO0000000003",
        "billId": 9491
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/21",
        "billId": 9987
      },
      {
        "state": "EU",
        "billNumber": "32005D0270",
        "billId": 546
      },
      {
        "state": "MN",
        "billNumber": "HF-3911",
        "billId": 4980
      },
      {
        "state": "PL",
        "billNumber": "DU/2020/797",
        "billId": 9979
      },
      {
        "state": "UK",
        "billNumber": "wsi/2011/551",
        "billId": 9821
      },
      {
        "state": "JP",
        "billNumber": "407CO0000000411",
        "billId": 9483
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047274648",
        "billId": 9473
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/1403",
        "billId": 9981
      },
      {
        "state": "UK",
        "billNumber": "uksi/2024/1332",
        "billId": 9740
      },
      {
        "state": "EU",
        "billNumber": "32021D1384",
        "billId": 774
      },
      {
        "state": "DK",
        "billNumber": "lta/2025/882",
        "billId": 10025
      }
    ]
  },
  {
    "lever": "labeling_marking",
    "name": "Labeling & Marking",
    "headline": "Apply required recyclability / disposal labeling",
    "direction": "Add chemical symbols (Hg, Cd, Pb) below bin symbol if hazardous thresholds exceeded.",
    "focus": [
      "Packaging",
      "Electronics",
      "Batteries",
      "Hazardous materials",
      "Organics",
      "Vehicles",
      "Textiles"
    ],
    "billCount": 222,
    "states": [
      "AT",
      "BR",
      "CH",
      "CL",
      "DC",
      "DE",
      "DK",
      "EE",
      "ES",
      "EU",
      "FI",
      "FR",
      "IE",
      "JP",
      "LT",
      "LU",
      "LV",
      "NL",
      "NY",
      "PL",
      "SE",
      "SI",
      "SK",
      "UK"
    ],
    "evidence": {
      "state": "NL",
      "bill": "BWBR0024492",
      "quote": "Batteries/accumulators containing >0.0005 wt% mercury, >0.002 wt% cadmium, or >0.004 wt% lead must bear the relevant chemical symbol (Hg, Cd, or Pb) below the crossed-out bin symbol, occupying at least one quarter of the symbol's dimensions (Articles 9(4)-(6))."
    },
    "feeImpact": {
      "malus": true,
      "bonus": true,
      "setJurisdictions": [
        "FR"
      ],
      "usPending": true,
      "examples": []
    },
    "bills": [
      {
        "state": "NL",
        "billNumber": "BWBR0024492",
        "billId": 9876
      },
      {
        "state": "FI",
        "billNumber": "2014/520",
        "billId": 10033
      },
      {
        "state": "JP",
        "billNumber": "413M60000400080",
        "billId": 9528
      },
      {
        "state": "JP",
        "billNumber": "413M60000400086",
        "billId": 9527
      },
      {
        "state": "JP",
        "billNumber": "413M60000400092",
        "billId": 9514
      },
      {
        "state": "NL",
        "billNumber": "BWBR0037392",
        "billId": 9866
      },
      {
        "state": "UK",
        "billNumber": "nisr/1995/122",
        "billId": 9794
      },
      {
        "state": "JP",
        "billNumber": "413M60000400090",
        "billId": 9515
      },
      {
        "state": "NL",
        "billNumber": "BWBR0006253",
        "billId": 9877
      },
      {
        "state": "EU",
        "billNumber": "32006L0066",
        "billId": 504
      },
      {
        "state": "JP",
        "billNumber": "413M60000400082",
        "billId": 9524
      },
      {
        "state": "JP",
        "billNumber": "413M60000400083",
        "billId": 9522
      },
      {
        "state": "JP",
        "billNumber": "413M60000400084",
        "billId": 9529
      },
      {
        "state": "JP",
        "billNumber": "413M60000400088",
        "billId": 9526
      },
      {
        "state": "JP",
        "billNumber": "413M60000400091",
        "billId": 9513
      },
      {
        "state": "JP",
        "billNumber": "413M60000C00001",
        "billId": 9538
      },
      {
        "state": "PL",
        "billNumber": "DU/2015/687",
        "billId": 10021
      },
      {
        "state": "AT",
        "billNumber": "20005815",
        "billId": 9955
      },
      {
        "state": "CH",
        "billNumber": "cc/2000/299",
        "billId": 9965
      },
      {
        "state": "CH",
        "billNumber": "cc/2021/633",
        "billId": 9962
      },
      {
        "state": "DE",
        "billNumber": "battg",
        "billId": 9844
      },
      {
        "state": "DK",
        "billNumber": "lta/2019/1218",
        "billId": 10029
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2015-1762",
        "billId": 9894
      },
      {
        "state": "EU",
        "billNumber": "32003D0138",
        "billId": 621
      },
      {
        "state": "EU",
        "billNumber": "32009R0641",
        "billId": 454
      },
      {
        "state": "EU",
        "billNumber": "32009R0767",
        "billId": 611
      },
      {
        "state": "EU",
        "billNumber": "32010R1103",
        "billId": 574
      },
      {
        "state": "EU",
        "billNumber": "32012L0019",
        "billId": 2
      },
      {
        "state": "EU",
        "billNumber": "32017R2279",
        "billId": 725
      },
      {
        "state": "EU",
        "billNumber": "32020R0762",
        "billId": 740
      },
      {
        "state": "EU",
        "billNumber": "32020R2151",
        "billId": 756
      },
      {
        "state": "EU",
        "billNumber": "32024L0232",
        "billId": 714
      },
      {
        "state": "EU",
        "billNumber": "32024L0884",
        "billId": 716
      },
      {
        "state": "EU",
        "billNumber": "32025R2269",
        "billId": 914
      },
      {
        "state": "FI",
        "billNumber": "2011/646",
        "billId": 10030
      },
      {
        "state": "FI",
        "billNumber": "2014/519",
        "billId": 10032
      },
      {
        "state": "FI",
        "billNumber": "2021/714",
        "billId": 10031
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000029958108",
        "billId": 9666
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000041553759",
        "billId": 9463
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000043714227",
        "billId": 9472
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000046005259",
        "billId": 9471
      },
      {
        "state": "IE",
        "billNumber": "eli/2024/si/33/made/en",
        "billId": 9946
      },
      {
        "state": "JP",
        "billNumber": "405M50000400034",
        "billId": 9495
      },
      {
        "state": "JP",
        "billNumber": "405M50000500001",
        "billId": 9494
      },
      {
        "state": "JP",
        "billNumber": "410AC0000000097",
        "billId": 846
      },
      {
        "state": "JP",
        "billNumber": "412M50000500001",
        "billId": 9501
      },
      {
        "state": "JP",
        "billNumber": "413M60000400078",
        "billId": 9509
      },
      {
        "state": "JP",
        "billNumber": "413M60000400079",
        "billId": 9506
      },
      {
        "state": "JP",
        "billNumber": "413M60000400085",
        "billId": 9525
      },
      {
        "state": "JP",
        "billNumber": "413M60000400087",
        "billId": 9521
      },
      {
        "state": "JP",
        "billNumber": "413M60000400089",
        "billId": 9523
      },
      {
        "state": "JP",
        "billNumber": "413M60000740001",
        "billId": 9541
      },
      {
        "state": "JP",
        "billNumber": "413M60000740002",
        "billId": 9542
      },
      {
        "state": "JP",
        "billNumber": "413M60001F40004",
        "billId": 9546
      },
      {
        "state": "JP",
        "billNumber": "414M60001400007",
        "billId": 9548
      },
      {
        "state": "LT",
        "billNumber": "TAIS.161216",
        "billId": 10054
      },
      {
        "state": "LV",
        "billNumber": "267716",
        "billId": 10048
      },
      {
        "state": "NL",
        "billNumber": "BWBR0004785",
        "billId": 9865
      },
      {
        "state": "NL",
        "billNumber": "BWBR0017053",
        "billId": 9872
      },
      {
        "state": "NL",
        "billNumber": "BWBR0034782",
        "billId": 9870
      },
      {
        "state": "NY",
        "billNumber": "S-5027C",
        "billId": 1100
      },
      {
        "state": "PL",
        "billNumber": "DU/2005/1495",
        "billId": 10011
      },
      {
        "state": "PL",
        "billNumber": "DU/2008/1464",
        "billId": 10010
      },
      {
        "state": "PL",
        "billNumber": "DU/2009/666",
        "billId": 10023
      },
      {
        "state": "PL",
        "billNumber": "DU/2013/1155",
        "billId": 10009
      },
      {
        "state": "PL",
        "billNumber": "DU/2015/1688",
        "billId": 10008
      },
      {
        "state": "PL",
        "billNumber": "DU/2018/1466",
        "billId": 10006
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/1895",
        "billId": 10005
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/521",
        "billId": 10017
      },
      {
        "state": "PL",
        "billNumber": "DU/2020/1893",
        "billId": 10004
      },
      {
        "state": "PL",
        "billNumber": "DU/2022/1113",
        "billId": 10013
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1852",
        "billId": 9992
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/1911",
        "billId": 9990
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/573",
        "billId": 10001
      },
      {
        "state": "SE",
        "billNumber": "sfs-2005-209",
        "billId": 9936
      },
      {
        "state": "SE",
        "billNumber": "sfs-2005-220",
        "billId": 9935
      },
      {
        "state": "SE",
        "billNumber": "sfs-2007-193",
        "billId": 9931
      },
      {
        "state": "SE",
        "billNumber": "sfs-2008-834",
        "billId": 9930
      },
      {
        "state": "SE",
        "billNumber": "sfs-2018-1462",
        "billId": 9919
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-1000",
        "billId": 9916
      },
      {
        "state": "SE",
        "billNumber": "sfs-2021-998",
        "billId": 9912
      },
      {
        "state": "SI",
        "billNumber": "2021-01-2724",
        "billId": 10061
      },
      {
        "state": "SI",
        "billNumber": "2024-01-2498",
        "billId": 10060
      },
      {
        "state": "SK",
        "billNumber": "2015/373",
        "billId": 10050
      },
      {
        "state": "SK",
        "billNumber": "2019/302",
        "billId": 10052
      },
      {
        "state": "UK",
        "billNumber": "ssi/2020/154",
        "billId": 9807
      },
      {
        "state": "UK",
        "billNumber": "ssi/2023/201",
        "billId": 9805
      },
      {
        "state": "UK",
        "billNumber": "ssi/2025/188",
        "billId": 9803
      },
      {
        "state": "UK",
        "billNumber": "ssi/2025/189",
        "billId": 9802
      },
      {
        "state": "UK",
        "billNumber": "uksi/1994/232",
        "billId": 9795
      },
      {
        "state": "UK",
        "billNumber": "uksi/2001/2551",
        "billId": 9792
      },
      {
        "state": "UK",
        "billNumber": "uksi/2012/1139",
        "billId": 9789
      },
      {
        "state": "UK",
        "billNumber": "uksi/2014/1771",
        "billId": 9774
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032847905",
        "billId": 9439
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-3",
        "billId": 9729
      },
      {
        "state": "DE",
        "billNumber": "elektrog_2015",
        "billId": 9843
      },
      {
        "state": "EU",
        "billNumber": "32009D0292",
        "billId": 684
      },
      {
        "state": "DK",
        "billNumber": "lta/2015/1453",
        "billId": 10027
      },
      {
        "state": "NL",
        "billNumber": "BWBR0007227",
        "billId": 9873
      },
      {
        "state": "NL",
        "billNumber": "BWBR0013707",
        "billId": 9883
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2008-2387",
        "billId": 9895
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2024-21709",
        "billId": 9899
      },
      {
        "state": "EU",
        "billNumber": "32024R1781",
        "billId": 8
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000029881868",
        "billId": 9673
      },
      {
        "state": "JP",
        "billNumber": "403AC0000000048",
        "billId": 847
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000110",
        "billId": 9480
      },
      {
        "state": "JP",
        "billNumber": "413M60000400073",
        "billId": 9505
      },
      {
        "state": "JP",
        "billNumber": "508M60001400002",
        "billId": 9569
      },
      {
        "state": "JP",
        "billNumber": "508M60001440001",
        "billId": 9570
      },
      {
        "state": "SE",
        "billNumber": "sfs-2007-185",
        "billId": 9932
      },
      {
        "state": "SI",
        "billNumber": "2010-01-0111",
        "billId": 10059
      },
      {
        "state": "SI",
        "billNumber": "2021-01-1053",
        "billId": 10057
      },
      {
        "state": "AT",
        "billNumber": "20002086",
        "billId": 9952
      },
      {
        "state": "DE",
        "billNumber": "altautov",
        "billId": 9847
      },
      {
        "state": "DE",
        "billNumber": "altholzv",
        "billId": 9852
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2021-5868",
        "billId": 9896
      },
      {
        "state": "EU",
        "billNumber": "32021R1929",
        "billId": 776
      },
      {
        "state": "EU",
        "billNumber": "32023L0544",
        "billId": 664
      },
      {
        "state": "EU",
        "billNumber": "32025R0040",
        "billId": 1
      },
      {
        "state": "FI",
        "billNumber": "2021/1029",
        "billId": 10034
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000026863961",
        "billId": 9669
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032770063",
        "billId": 9668
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000045072868",
        "billId": 9435
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000046664100",
        "billId": 9454
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10",
        "billId": 9725
      },
      {
        "state": "JP",
        "billNumber": "410CO0000000378",
        "billId": 9484
      },
      {
        "state": "JP",
        "billNumber": "413M60000400062",
        "billId": 9533
      },
      {
        "state": "JP",
        "billNumber": "413M60000400070",
        "billId": 9511
      },
      {
        "state": "JP",
        "billNumber": "413M60000400071",
        "billId": 9503
      },
      {
        "state": "JP",
        "billNumber": "413M60000400072",
        "billId": 9507
      },
      {
        "state": "JP",
        "billNumber": "413M60000400074",
        "billId": 9512
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/2022/06/09/a266/jo/fr",
        "billId": 10038
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/rgd/2018/07/02/a562/jo/fr",
        "billId": 10041
      },
      {
        "state": "LV",
        "billNumber": "57207",
        "billId": 10046
      },
      {
        "state": "NL",
        "billNumber": "BWBR0018139",
        "billId": 9868
      },
      {
        "state": "NL",
        "billNumber": "BWBR0032405",
        "billId": 9871
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1658",
        "billId": 9993
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/927",
        "billId": 9991
      },
      {
        "state": "SE",
        "billNumber": "sfs-2023-132",
        "billId": 9909
      },
      {
        "state": "UK",
        "billNumber": "uksi/2015/63",
        "billId": 9788
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/283/made/en",
        "billId": 9948
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-18",
        "billId": 9731
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2022-5809",
        "billId": 9892
      },
      {
        "state": "EU",
        "billNumber": "32000L0053",
        "billId": 6
      },
      {
        "state": "JP",
        "billNumber": "413M60000400063",
        "billId": 9531
      },
      {
        "state": "JP",
        "billNumber": "413M60000400068",
        "billId": 9535
      },
      {
        "state": "JP",
        "billNumber": "418M60000740001",
        "billId": 9553
      },
      {
        "state": "JP",
        "billNumber": "420M60000600001",
        "billId": 9556
      },
      {
        "state": "JP",
        "billNumber": "508M60001400003",
        "billId": 9568
      },
      {
        "state": "NL",
        "billNumber": "BWBR0024500",
        "billId": 9875
      },
      {
        "state": "UK",
        "billNumber": "uksi/1999/3447",
        "billId": 9762
      },
      {
        "state": "EE",
        "billNumber": "113032019103",
        "billId": 10043
      },
      {
        "state": "EE",
        "billNumber": "749804",
        "billId": 10042
      },
      {
        "state": "EU",
        "billNumber": "32025R0606",
        "billId": 913
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000042837821",
        "billId": 9411
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000044155771",
        "billId": 9605
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000049375942",
        "billId": 9458
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000050749111",
        "billId": 9466
      },
      {
        "state": "JP",
        "billNumber": "413M60000400067",
        "billId": 9530
      },
      {
        "state": "JP",
        "billNumber": "413M60000400069",
        "billId": 9532
      },
      {
        "state": "JP",
        "billNumber": "413M60000400075",
        "billId": 9508
      },
      {
        "state": "JP",
        "billNumber": "413M60000C00004",
        "billId": 9539
      },
      {
        "state": "JP",
        "billNumber": "425M60001000005",
        "billId": 9557
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/2017/03/21/a330/jo/fr",
        "billId": 10037
      },
      {
        "state": "NL",
        "billNumber": "BWBR0048299",
        "billId": 9860
      },
      {
        "state": "SE",
        "billNumber": "sfs-2009-1031",
        "billId": 9928
      },
      {
        "state": "SE",
        "billNumber": "sfs-2025-813",
        "billId": 9910
      },
      {
        "state": "UK",
        "billNumber": "uksi/2000/3097",
        "billId": 9793
      },
      {
        "state": "UK",
        "billNumber": "uksi/2003/2635",
        "billId": 9743
      },
      {
        "state": "UK",
        "billNumber": "uksi/2015/1935",
        "billId": 9784
      },
      {
        "state": "EU",
        "billNumber": "31997D0129",
        "billId": 633
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/542",
        "billId": 9996
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000052450618",
        "billId": 9597
      },
      {
        "state": "DK",
        "billNumber": "lta/2019/1337",
        "billId": 10028
      },
      {
        "state": "CL",
        "billNumber": "1090894",
        "billId": 9900
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2006-9832",
        "billId": 9898
      },
      {
        "state": "EU",
        "billNumber": "32005L0064",
        "billId": 455
      },
      {
        "state": "EU",
        "billNumber": "32008L0033",
        "billId": 672
      },
      {
        "state": "EU",
        "billNumber": "32017L2102",
        "billId": 712
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/281/made/en",
        "billId": 9950
      },
      {
        "state": "JP",
        "billNumber": "345AC0000000137",
        "billId": 9479
      },
      {
        "state": "JP",
        "billNumber": "413M60001500001",
        "billId": 9502
      },
      {
        "state": "LT",
        "billNumber": "TAIS.59267",
        "billId": 10053
      },
      {
        "state": "SE",
        "billNumber": "sfs-1997-788",
        "billId": 9944
      },
      {
        "state": "UK",
        "billNumber": "uksi/2025/1369",
        "billId": 9744
      },
      {
        "state": "DK",
        "billNumber": "lta/2025/1146",
        "billId": 10024
      },
      {
        "state": "EU",
        "billNumber": "32026R0296",
        "billId": 929
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000025423069",
        "billId": 9667
      },
      {
        "state": "JP",
        "billNumber": "413M60000400059",
        "billId": 9517
      },
      {
        "state": "JP",
        "billNumber": "425M60001400003",
        "billId": 9558
      },
      {
        "state": "JP",
        "billNumber": "508M60000740004",
        "billId": 9582
      },
      {
        "state": "LV",
        "billNumber": "221378",
        "billId": 10045
      },
      {
        "state": "SE",
        "billNumber": "sfs-2007-186",
        "billId": 9933
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000019074839",
        "billId": 9593
      },
      {
        "state": "LT",
        "billNumber": "TAIS.325345",
        "billId": 10056
      },
      {
        "state": "NL",
        "billNumber": "BWBR0046477",
        "billId": 9885
      },
      {
        "state": "EU",
        "billNumber": "32025L1892",
        "billId": 841
      },
      {
        "state": "BR",
        "billNumber": "_ato2023-2026/2023/decreto/D11413.htm",
        "billId": 9959
      },
      {
        "state": "BR",
        "billNumber": "_ato2023-2026/2025/decreto/D12688.htm",
        "billId": 9960
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000029387124",
        "billId": 9635
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/149/made/en",
        "billId": 9947
      },
      {
        "state": "NL",
        "billNumber": "BWBR0050381",
        "billId": 9861
      },
      {
        "state": "NY",
        "billNumber": "S-7552",
        "billId": 3378
      },
      {
        "state": "PL",
        "billNumber": "DU/2023/1587",
        "billId": 9969
      },
      {
        "state": "UK",
        "billNumber": "nisr/2023/25",
        "billId": 9783
      },
      {
        "state": "EU",
        "billNumber": "32014D0955",
        "billId": 652
      },
      {
        "state": "NY",
        "billNumber": "S-2097",
        "billId": 3659
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/1648",
        "billId": 9977
      },
      {
        "state": "SE",
        "billNumber": "sfs-2000-208",
        "billId": 9938
      },
      {
        "state": "SE",
        "billNumber": "sfs-2001-1063",
        "billId": 9937
      },
      {
        "state": "DC",
        "billNumber": "D.C. Law 24-320",
        "billId": 4798
      },
      {
        "state": "NY",
        "billNumber": "S-5663",
        "billId": 3778
      },
      {
        "state": "NY",
        "billNumber": "S-73",
        "billId": 4602
      },
      {
        "state": "UK",
        "billNumber": "uksi/2009/890",
        "billId": 9742
      },
      {
        "state": "EU",
        "billNumber": "32001D0118",
        "billId": 695
      },
      {
        "state": "PL",
        "billNumber": "DU/2019/1403",
        "billId": 9981
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/779",
        "billId": 9978
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000116",
        "billId": 851
      },
      {
        "state": "NY",
        "billNumber": "A-8195",
        "billId": 3857
      },
      {
        "state": "PL",
        "billNumber": "DU/2020/797",
        "billId": 9979
      },
      {
        "state": "EU",
        "billNumber": "32024R1252",
        "billId": 859
      },
      {
        "state": "NY",
        "billNumber": "A-4641",
        "billId": 2066
      }
    ]
  },
  {
    "lever": "compostability",
    "name": "Compostability",
    "headline": "Use certified-compostable materials where specified",
    "direction": "Do not label industrial-only compostable packaging as 'compostable'.",
    "focus": [
      "Packaging",
      "Organics",
      "Biobased",
      "Textiles",
      "Electronics",
      "Batteries",
      "Construction"
    ],
    "billCount": 18,
    "states": [
      "CA",
      "CZ",
      "EU",
      "FR",
      "JP",
      "NY",
      "PL",
      "UK",
      "WA"
    ],
    "evidence": {
      "state": "FR",
      "bill": "JORFTEXT000041553759",
      "quote": "Prohibition: plastic products and packaging whose compostability can only be achieved in industrial composting units may NOT bear the label 'compostable' (Art. 13)"
    },
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
        "state": "FR",
        "billNumber": "JORFTEXT000041553759",
        "billId": 9463
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000042753962",
        "billId": 9455
      },
      {
        "state": "NY",
        "billNumber": "S-5062",
        "billId": 3596
      },
      {
        "state": "EU",
        "billNumber": "32025R0040",
        "billId": 1
      },
      {
        "state": "CA",
        "billNumber": "SB-279",
        "billId": 4120
      },
      {
        "state": "EU",
        "billNumber": "32018L0852",
        "billId": 627
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000027947087",
        "billId": 9654
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032187830",
        "billId": 9636
      },
      {
        "state": "UK",
        "billNumber": "wsi/2011/551",
        "billId": 9821
      },
      {
        "state": "CZ",
        "billNumber": "2020/541",
        "billId": 10063
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/1648",
        "billId": 9977
      },
      {
        "state": "EU",
        "billNumber": "32018L0850",
        "billId": 626
      },
      {
        "state": "JP",
        "billNumber": "413M60001200002",
        "billId": 9544
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000036396791",
        "billId": 9643
      },
      {
        "state": "UK",
        "billNumber": "ukpga/2003/29",
        "billId": 9808
      },
      {
        "state": "WA",
        "billNumber": "SB-5284",
        "billId": 1080
      },
      {
        "state": "CA",
        "billNumber": "AB-1857",
        "billId": 3418
      },
      {
        "state": "EU",
        "billNumber": "31999L0031",
        "billId": 451
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
      "Vehicles",
      "Textiles",
      "Organics"
    ],
    "billCount": 115,
    "states": [
      "AT",
      "CL",
      "CZ",
      "DE",
      "DK",
      "ES",
      "EU",
      "FI",
      "FR",
      "IE",
      "JP",
      "LT",
      "LU",
      "ME",
      "NL",
      "NY",
      "PL",
      "SC",
      "SE",
      "SI",
      "UK",
      "WA"
    ],
    "evidence": {
      "state": "EU",
      "bill": "32011L0065",
      "quote": "Ensure spare parts are available for product reuse, refurbishment, and lifetime extension"
    },
    "feeImpact": {
      "malus": true,
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
        "billId": 510
      },
      {
        "state": "JP",
        "billNumber": "413M60000400063",
        "billId": 9531
      },
      {
        "state": "JP",
        "billNumber": "413M60000400068",
        "billId": 9535
      },
      {
        "state": "JP",
        "billNumber": "413M60000400070",
        "billId": 9511
      },
      {
        "state": "JP",
        "billNumber": "413M60000400071",
        "billId": 9503
      },
      {
        "state": "JP",
        "billNumber": "413M60000400072",
        "billId": 9507
      },
      {
        "state": "JP",
        "billNumber": "413M60000400073",
        "billId": 9505
      },
      {
        "state": "JP",
        "billNumber": "413M60000400074",
        "billId": 9512
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2025-17186",
        "billId": 9897
      },
      {
        "state": "EU",
        "billNumber": "32024R1781",
        "billId": 8
      },
      {
        "state": "FI",
        "billNumber": "2011/646",
        "billId": 10030
      },
      {
        "state": "FI",
        "billNumber": "2014/519",
        "billId": 10032
      },
      {
        "state": "FI",
        "billNumber": "2021/714",
        "billId": 10031
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000029881868",
        "billId": 9673
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000032610837",
        "billId": 9468
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000042837821",
        "billId": 9411
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000044513913",
        "billId": 9434
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000044806559",
        "billId": 9670
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000045072860",
        "billId": 9671
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000049375942",
        "billId": 9458
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000050000979",
        "billId": 9415
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10",
        "billId": 9725
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-4",
        "billId": 9722
      },
      {
        "state": "JP",
        "billNumber": "412AC0000000110",
        "billId": 9480
      },
      {
        "state": "JP",
        "billNumber": "413M60000400062",
        "billId": 9533
      },
      {
        "state": "JP",
        "billNumber": "413M60000400064",
        "billId": 9537
      },
      {
        "state": "JP",
        "billNumber": "413M60000400065",
        "billId": 9534
      },
      {
        "state": "JP",
        "billNumber": "413M60000400066",
        "billId": 9536
      },
      {
        "state": "JP",
        "billNumber": "413M60000400067",
        "billId": 9530
      },
      {
        "state": "JP",
        "billNumber": "413M60000400069",
        "billId": 9532
      },
      {
        "state": "JP",
        "billNumber": "413M60000400075",
        "billId": 9508
      },
      {
        "state": "JP",
        "billNumber": "413M60000400079",
        "billId": 9506
      },
      {
        "state": "JP",
        "billNumber": "413M60000C00004",
        "billId": 9539
      },
      {
        "state": "LU",
        "billNumber": "eli/etat/leg/loi/2022/06/09/a266/jo/fr",
        "billId": 10038
      },
      {
        "state": "SE",
        "billNumber": "sfs-2005-209",
        "billId": 9936
      },
      {
        "state": "UK",
        "billNumber": "uksi/1994/232",
        "billId": 9795
      },
      {
        "state": "DE",
        "billNumber": "battdg",
        "billId": 9845
      },
      {
        "state": "JP",
        "billNumber": "413M60000400080",
        "billId": 9528
      },
      {
        "state": "JP",
        "billNumber": "413M60000400083",
        "billId": 9522
      },
      {
        "state": "JP",
        "billNumber": "413M60000C00001",
        "billId": 9538
      },
      {
        "state": "NL",
        "billNumber": "BWBR0007227",
        "billId": 9873
      },
      {
        "state": "JP",
        "billNumber": "413M60000400084",
        "billId": 9529
      },
      {
        "state": "AT",
        "billNumber": "20005815",
        "billId": 9955
      },
      {
        "state": "DE",
        "billNumber": "elektrog_2015",
        "billId": 9843
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000026863961",
        "billId": 9669
      },
      {
        "state": "ME",
        "billNumber": "LD-474",
        "billId": 1081
      },
      {
        "state": "NL",
        "billNumber": "BWBR0017053",
        "billId": 9872
      },
      {
        "state": "NL",
        "billNumber": "BWBR0034782",
        "billId": 9870
      },
      {
        "state": "NY",
        "billNumber": "S-5027C",
        "billId": 1100
      },
      {
        "state": "PL",
        "billNumber": "DU/2014/1322",
        "billId": 10022
      },
      {
        "state": "PL",
        "billNumber": "DU/2022/1113",
        "billId": 10013
      },
      {
        "state": "PL",
        "billNumber": "DU/2024/573",
        "billId": 10001
      },
      {
        "state": "SI",
        "billNumber": "2010-01-0111",
        "billId": 10059
      },
      {
        "state": "UK",
        "billNumber": "uksi/2015/63",
        "billId": 9788
      },
      {
        "state": "NL",
        "billNumber": "BWBR0044197",
        "billId": 9859
      },
      {
        "state": "NL",
        "billNumber": "BWBR0048299",
        "billId": 9860
      },
      {
        "state": "DK",
        "billNumber": "lta/2014/130",
        "billId": 10026
      },
      {
        "state": "EU",
        "billNumber": "32016L0585",
        "billId": 602
      },
      {
        "state": "JP",
        "billNumber": "504M60007FFE001",
        "billId": 9562
      },
      {
        "state": "JP",
        "billNumber": "508M60000400011",
        "billId": 9574
      },
      {
        "state": "JP",
        "billNumber": "413M60001400001",
        "billId": 9540
      },
      {
        "state": "EU",
        "billNumber": "32012L0019",
        "billId": 2
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-3",
        "billId": 9729
      },
      {
        "state": "EU",
        "billNumber": "32020L0363",
        "billId": 525
      },
      {
        "state": "JP",
        "billNumber": "508M60000400008",
        "billId": 9573
      },
      {
        "state": "DE",
        "billNumber": "altautov",
        "billId": 9847
      },
      {
        "state": "EU",
        "billNumber": "32005L0064",
        "billId": 455
      },
      {
        "state": "EU",
        "billNumber": "32009R0641",
        "billId": 454
      },
      {
        "state": "EU",
        "billNumber": "32017L2102",
        "billId": 712
      },
      {
        "state": "EU",
        "billNumber": "32026R0296",
        "billId": 929
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000045072868",
        "billId": 9435
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-24",
        "billId": 9735
      },
      {
        "state": "FR",
        "billNumber": "cenv/L541-10-26",
        "billId": 9737
      },
      {
        "state": "JP",
        "billNumber": "405M50000400034",
        "billId": 9495
      },
      {
        "state": "JP",
        "billNumber": "405M50000500001",
        "billId": 9494
      },
      {
        "state": "JP",
        "billNumber": "410AC0000000097",
        "billId": 846
      },
      {
        "state": "UK",
        "billNumber": "nisr/2006/519",
        "billId": 9778
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000041553759",
        "billId": 9463
      },
      {
        "state": "NL",
        "billNumber": "BWBR0032405",
        "billId": 9871
      },
      {
        "state": "WA",
        "billNumber": "SB-5144",
        "billId": 993
      },
      {
        "state": "NL",
        "billNumber": "BWBR0016990",
        "billId": 9869
      },
      {
        "state": "ES",
        "billNumber": "BOE-A-2015-1762",
        "billId": 9894
      },
      {
        "state": "NY",
        "billNumber": "S-3217",
        "billId": 3115
      },
      {
        "state": "DK",
        "billNumber": "lta/2019/1337",
        "billId": 10028
      },
      {
        "state": "LT",
        "billNumber": "TAIS.59267",
        "billId": 10053
      },
      {
        "state": "EU",
        "billNumber": "32025L1892",
        "billId": 841
      },
      {
        "state": "PL",
        "billNumber": "DU/2021/2151",
        "billId": 9975
      },
      {
        "state": "EU",
        "billNumber": "32019D0665",
        "billId": 764
      },
      {
        "state": "JP",
        "billNumber": "403AC0000000048",
        "billId": 847
      },
      {
        "state": "JP",
        "billNumber": "508M60000400007",
        "billId": 9571
      },
      {
        "state": "SI",
        "billNumber": "2024-01-2498",
        "billId": 10060
      },
      {
        "state": "UK",
        "billNumber": "uksi/2005/263",
        "billId": 9755
      },
      {
        "state": "EU",
        "billNumber": "32018L0852",
        "billId": 627
      },
      {
        "state": "JP",
        "billNumber": "508M60000400009",
        "billId": 9572
      },
      {
        "state": "JP",
        "billNumber": "508M60000400010",
        "billId": 9576
      },
      {
        "state": "JP",
        "billNumber": "508M60001400003",
        "billId": 9568
      },
      {
        "state": "SC",
        "billNumber": "S-171",
        "billId": 997
      },
      {
        "state": "UK",
        "billNumber": "wsi/2011/551",
        "billId": 9821
      },
      {
        "state": "CL",
        "billNumber": "1154847",
        "billId": 9901
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000033691469",
        "billId": 9586
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000042575740",
        "billId": 9430
      },
      {
        "state": "JP",
        "billNumber": "503AC0000000060",
        "billId": 849
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047439314",
        "billId": 9476
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000052450618",
        "billId": 9597
      },
      {
        "state": "SE",
        "billNumber": "sfs-1997-788",
        "billId": 9944
      },
      {
        "state": "DE",
        "billNumber": "krwg",
        "billId": 9846
      },
      {
        "state": "EU",
        "billNumber": "32019D2193",
        "billId": 779
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000029387124",
        "billId": 9635
      },
      {
        "state": "FR",
        "billNumber": "JORFTEXT000047476672",
        "billId": 9418
      },
      {
        "state": "CZ",
        "billNumber": "2020/542",
        "billId": 10064
      },
      {
        "state": "IE",
        "billNumber": "eli/2014/si/149/made/en",
        "billId": 9947
      },
      {
        "state": "NY",
        "billNumber": "A-6193",
        "billId": 3105
      },
      {
        "state": "SE",
        "billNumber": "sfs-2023-133",
        "billId": 9908
      },
      {
        "state": "NL",
        "billNumber": "BWBR0045640",
        "billId": 9863
      },
      {
        "state": "JP",
        "billNumber": "508M60001740001",
        "billId": 9580
      }
    ]
  }
];
