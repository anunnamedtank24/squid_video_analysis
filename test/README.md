此為 202605211317 ~ 202605211359 的結果

在本地路徑為
project/
├── assets/2026052122/2026052113/
│   ├── 17{...}.mp4
│   ├── ...
│   └── 59{...}.mp4
└── output/202605211317_202605211359/
    ├── part_1.5
    ├── ...

再執行
cd project
mkdir -p test/assets/2026052122/
cp -r assets/2026052122/2026052113/ test/assets/2026052122/
mkdir -p test/output/
cp -r output/202605211317_202605211359/ test/output/