# Évaluation indicative

Pertinence = le titre de l'arrêt contient un mot-clé du thème (voir `evaluer.py`).

Thèmes : « نزاع التحفيظ والتعرض » (94 docs pertinents) ; « دعوى الإفراغ والطرد من المحل » (27 docs pertinents) ; « الشفعة » (10 docs pertinents) ; « قسمة التركة بين الورثة » (37 docs pertinents) ; « الخبرة القضائية وسلطة المحكمة » (27 docs pertinents) ; « التقييد الاحتياطي » (9 docs pertinents) ; « اختصاص المحكمة » (11 docs pertinents) ; « استحقاق العقار » (38 docs pertinents)

## 1. Stemming × mesure de similarité (TF = log)

| Stemming | Mesure | P@10 | MAP |
|---|---|---|---|
| none | cosinus | 0.525 | 0.509 |
| none | produit | 0.575 | 0.535 |
| none | jaccard | 0.512 | 0.426 |
| none | dice | 0.512 | 0.426 |
| none | euclidienne | 0.188 | 0.244 |
| light10 | cosinus | 0.600 | 0.589 |
| light10 | produit | 0.575 | 0.592 |
| light10 | jaccard | 0.362 | 0.366 |
| light10 | dice | 0.362 | 0.366 |
| light10 | euclidienne | 0.138 | 0.196 |

## 2. Schéma TF (stemming = light10, mesure = cosinus)

| TF | P@10 | MAP |
|---|---|---|
| raw | 0.600 | 0.644 |
| log | 0.600 | 0.589 |
| norm | 0.600 | 0.644 |
