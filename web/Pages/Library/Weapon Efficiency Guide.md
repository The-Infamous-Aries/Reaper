# 🚀 Weapon Efficiency Guide

## **1\. Executive Summary: The "Money War"**

In any conflict, we measure success by **Net Resource Drain**. A strike is only successful if the cost of the weapon is lower than the cost for the enemy to repair the damage.

* **Standard Nuke Cost:** \~$16,000,000  
* **Standard Missile Cost:** \~$1,500,000

---

## **2\. Infrastructure Damage Formulas**

Damage is not flat. It is governed by a "City Infra Limit" ($L$), meaning the less infrastructure a target has, the less damage your weapons can physically do.

### **Missile Damage**

**Formula:** $\\min(\\text{RAND}(300, 350), (0.3 \\times \\text{Current Infra}) \+ 100)$

* **The Bottom Line:** If a target is under **750 Infra**, missiles are capped and lose efficiency.

### **Nuke Damage**

**Formula:** $\\min(\\text{RAND}(1700, 2000), (0.8 \\times \\text{Current Infra}) \+ 150)$

* **The Bottom Line:** If a target is under **2,100 Infra**, nukes are capped and lose efficiency.

---

## **3\. Efficiency Thresholds (Targeting Guide)**

Use this table to determine if a target is worth the cost of the ordinance. The **"Min Infra"** column shows the level the target must be at **before** you fire.

| Damage Multiplier | Total Value Destroyed | Nuke Target (Min Infra) | Missile Target (Min Infra) |
| :---- | :---- | :---- | :---- |
| **1x (Break-Even)** | $1.5M (M) / $16M (N) | **2,036** | **1,102** |
| **2x (Efficient)** | $32M \- Nuke $3.0M \- Missile | **2,535** | **1,452** |
| **3x (Great)** | $48M \- Nuke $4.5M \- Missile  | **2,894** | **1,710** |
| **5x (Excellent)** | $80M \- Nuke $7.5M \- Missile | **3,439** | **2,108** |
| **10x (God-Tier)** | $160M Nuke $15M Missile | **4,398** | **2,817** |
| **20x (Nuclear Winter)** | $320M \- Nuke $30M \- Missile | **5,697** | **3,785** |

---

## **4\. Strategic Rules of Engagement (ROE)**

### **Rule 1: The "Missile Priority" Zone (1,100 – 2,000 Infra)**

At this range, missiles are your primary profit-maker.

* **DO:** Use missiles to drain the enemy’s treasury.  
* **DON'T:** Use nukes unless it is a high-priority military target (e.g., clearing aircraft for a ground rush).

### **Rule 2: The "Nuke Sweet Spot" (3,000+ Infra)**

This is where nukes become game-changing.

* **Return on Investment:** A single nuke on a 3,500 infra city destroys **$80,000,000** in value.  
* **Effect:** One hit in this bracket does more economic damage than 50 successful ground attacks.

### **Rule 3: The "Red Zone" (Under 1,100 Infra)**

* **Warning:** At this level, you are losing money on every shot.  
* **Action:** If a target has been hammered down to 1,000 infra, **cease all missile and nuke fire**. Switch to ground operations or move to a fresh target.

---

## **5\. Technical Math Reference**

For those using spreadsheets or Discord bots, the base unit cost for 1 point of infrastructure ($C$) is:

$$C \= \\frac{(\\text{Current Infra} \- 10)^{2.2}}{710} \+ 300$$  
---

