#!/usr/bin/env python3
"""
4D Lottery Number Checker — Flask web app.
Reads lot_results.json and lets users check a 4-digit number for prizes.
"""

import json
import math
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

RESULTS_FILE    = os.path.join(os.path.dirname(__file__), "lot_results.json")
MY_NUMBERS_FILE = os.path.join(os.path.dirname(__file__), "my_numbers.json")
DREAM_DICT_FILE = os.path.join(os.path.dirname(__file__), "dream_dict.json")

# Traditional Malaysian Chinese 4D dream book (万字梦书) seed associations.
# Keys are lowercase English keywords; nums are 4-digit strings.
DREAM_SEED: dict = {
    # ── Animals ──
    "snake":       {"label": "Snake (蛇)",           "nums": ["0013","2121","1313","3456","2300"], "explanation": "Snake is a common dream omen associated with fortune and hidden danger."},
    "serpent":     {"label": "Snake (蛇)",           "nums": ["0013","2121","1313","3456","2300"], "explanation": ""},
    "cobra":       {"label": "Snake (蛇)",           "nums": ["0013","2121","1313","3456","2300"], "explanation": ""},
    "python":      {"label": "Snake (蛇)",           "nums": ["0013","2121","1313","3456","2300"], "explanation": ""},
    "tiger":       {"label": "Tiger (虎)",           "nums": ["0124","1234","2345","6262","0262"], "explanation": "Tiger symbolises power and protection in Chinese tradition."},
    "dog":         {"label": "Dog (狗)",             "nums": ["0169","1690","6900","9016","0016"], "explanation": "Dog is a loyal companion and represents faithfulness."},
    "puppy":       {"label": "Dog (狗)",             "nums": ["0169","1690","6900","9016","0016"], "explanation": ""},
    "cat":         {"label": "Cat (猫)",             "nums": ["0236","2360","3600","6003","0023"], "explanation": "Cat represents curiosity and good fortune in dreams."},
    "kitten":      {"label": "Cat (猫)",             "nums": ["0236","2360","3600","6003","0023"], "explanation": ""},
    "rat":         {"label": "Rat/Mouse (鼠)",       "nums": ["0015","1500","5001","0150","5100"], "explanation": "Rat is the first zodiac animal and linked to resourcefulness."},
    "mouse":       {"label": "Rat/Mouse (鼠)",       "nums": ["0015","1500","5001","0150","5100"], "explanation": ""},
    "pig":         {"label": "Pig (猪)",             "nums": ["0070","0700","7001","0007","7070"], "explanation": "Pig symbolises wealth and abundance."},
    "boar":        {"label": "Pig (猪)",             "nums": ["0070","0700","7001","0007","7070"], "explanation": ""},
    "rabbit":      {"label": "Rabbit (兔)",          "nums": ["0218","2180","1802","8021","0082"], "explanation": "Rabbit is linked to luck and the moon goddess."},
    "bunny":       {"label": "Rabbit (兔)",          "nums": ["0218","2180","1802","8021","0082"], "explanation": ""},
    "hare":        {"label": "Rabbit (兔)",          "nums": ["0218","2180","1802","8021","0082"], "explanation": ""},
    "dragon":      {"label": "Dragon (龙)",          "nums": ["0008","0808","8080","0800","8008"], "explanation": "Dragon is the luckiest of all zodiac signs; 8 is a prosperous digit."},
    "horse":       {"label": "Horse (马)",           "nums": ["0012","1200","2100","0120","1020"], "explanation": "Horse represents speed, freedom and success."},
    "monkey":      {"label": "Monkey (猴)",          "nums": ["0056","5600","6005","0560","5006"], "explanation": "Monkey is clever and associated with trickery and fortune."},
    "rooster":     {"label": "Rooster/Chicken (鸡)", "nums": ["0009","0900","9009","9090","0099"], "explanation": "Rooster heralds a new day and good news."},
    "chicken":     {"label": "Rooster/Chicken (鸡)", "nums": ["0009","0900","9009","9090","0099"], "explanation": ""},
    "hen":         {"label": "Rooster/Chicken (鸡)", "nums": ["0009","0900","9009","9090","0099"], "explanation": ""},
    "ox":          {"label": "Ox/Cow (牛)",          "nums": ["0021","0210","2100","1200","2010"], "explanation": "Ox symbolises hard work and steady progress."},
    "cow":         {"label": "Ox/Cow (牛)",          "nums": ["0021","0210","2100","1200","2010"], "explanation": ""},
    "buffalo":     {"label": "Ox/Cow (牛)",          "nums": ["0021","0210","2100","1200","2010"], "explanation": ""},
    "goat":        {"label": "Goat/Sheep (羊)",      "nums": ["0019","0190","1900","9001","9100"], "explanation": "Goat represents gentleness and peace."},
    "sheep":       {"label": "Goat/Sheep (羊)",      "nums": ["0019","0190","1900","9001","9100"], "explanation": ""},
    "fish":        {"label": "Fish (鱼)",            "nums": ["0150","1500","5001","0015","0501"], "explanation": "Fish (鱼) sounds like surplus (余) — a strong wealth omen."},
    "bird":        {"label": "Bird (鸟)",            "nums": ["0108","1080","8010","0018","1008"], "explanation": "Bird in a dream often means good news is coming."},
    "sparrow":     {"label": "Bird (鸟)",            "nums": ["0108","1080","8010","0018","1008"], "explanation": ""},
    "pigeon":      {"label": "Bird (鸟)",            "nums": ["0108","1080","8010","0018","1008"], "explanation": ""},
    "dove":        {"label": "Bird (鸟)",            "nums": ["0108","1080","8010","0018","1008"], "explanation": ""},
    "crow":        {"label": "Crow (乌鸦)",          "nums": ["0043","0430","4300","3004","0403"], "explanation": "Crow is a warning omen in Chinese tradition."},
    "raven":       {"label": "Crow (乌鸦)",          "nums": ["0043","0430","4300","3004","0403"], "explanation": ""},
    "owl":         {"label": "Owl (猫头鹰)",         "nums": ["0205","2050","5002","0520","2500"], "explanation": "Owl is an omen of change or warning."},
    "eagle":       {"label": "Eagle (鹰)",           "nums": ["0089","0890","8900","9008","0809"], "explanation": "Eagle soaring means ambition and great achievement ahead."},
    "hawk":        {"label": "Eagle (鹰)",           "nums": ["0089","0890","8900","9008","0809"], "explanation": ""},
    "frog":        {"label": "Frog (青蛙)",          "nums": ["0174","1740","4017","7401","1047"], "explanation": "Frog (蛙) sounds like wealth (发) in some dialects."},
    "toad":        {"label": "Frog (青蛙)",          "nums": ["0174","1740","4017","7401","1047"], "explanation": ""},
    "elephant":    {"label": "Elephant (象)",        "nums": ["0026","0260","2600","6002","0602"], "explanation": "Elephant brings wisdom and good luck."},
    "lion":        {"label": "Lion (狮)",            "nums": ["0045","0450","4500","5004","0054"], "explanation": "Lion guards the door against evil spirits."},
    "bear":        {"label": "Bear (熊)",            "nums": ["0368","3680","6803","8036","3068"], "explanation": "Bear in a dream signals strength and protection."},
    "crocodile":   {"label": "Crocodile (鳄鱼)",    "nums": ["0090","0900","9000","0009","9090"], "explanation": "Crocodile is a danger sign but also hidden wealth."},
    "alligator":   {"label": "Crocodile (鳄鱼)",    "nums": ["0090","0900","9000","0009","9090"], "explanation": ""},
    "turtle":      {"label": "Turtle/Tortoise (龟)", "nums": ["0288","2880","8802","0828","2808"], "explanation": "Turtle is the symbol of longevity and enduring luck."},
    "tortoise":    {"label": "Turtle/Tortoise (龟)", "nums": ["0288","2880","8802","0828","2808"], "explanation": ""},
    "spider":      {"label": "Spider (蜘蛛)",        "nums": ["0302","3020","0230","2003","3002"], "explanation": "Spider weaving a web signals wealth being woven."},
    "ant":         {"label": "Ant (蚂蚁)",           "nums": ["0039","0390","3900","9003","0309"], "explanation": "Ants in large numbers signal hard work paying off."},
    "bee":         {"label": "Bee (蜜蜂)",           "nums": ["0093","0930","9300","3009","0093"], "explanation": "Bee brings sweet rewards and industry."},
    "butterfly":   {"label": "Butterfly (蝴蝶)",     "nums": ["0186","1860","6018","8601","1068"], "explanation": "Butterfly represents transformation and beauty."},
    "mosquito":    {"label": "Mosquito (蚊子)",      "nums": ["0017","0170","1700","7001","1070"], "explanation": "Mosquito signals small annoyances or petty loss."},
    "centipede":   {"label": "Centipede (蜈蚣)",     "nums": ["0071","0710","7100","1007","0107"], "explanation": "Centipede is a yin creature signalling hidden paths."},
    "scorpion":    {"label": "Scorpion (蝎子)",      "nums": ["0064","0640","6400","4006","0604"], "explanation": "Scorpion warns of a hidden enemy or trap."},
    "crab":        {"label": "Crab (螃蟹)",          "nums": ["0330","3300","3030","0033","3003"], "explanation": "Crab walks sideways — wealth may come from unexpected direction."},
    "prawn":       {"label": "Prawn/Shrimp (虾)",    "nums": ["0303","3030","3003","0033","3300"], "explanation": ""},
    "shrimp":      {"label": "Prawn/Shrimp (虾)",    "nums": ["0303","3030","3003","0033","3300"], "explanation": ""},
    "lizard":      {"label": "Lizard (蜥蜴)",        "nums": ["0074","0740","7400","4007","0407"], "explanation": "Lizard appearing on the wall is a common household omen."},
    "gecko":       {"label": "Lizard (蜥蜴)",        "nums": ["0074","0740","7400","4007","0407"], "explanation": ""},
    "deer":        {"label": "Deer (鹿)",            "nums": ["0058","0580","5800","8005","0508"], "explanation": "Deer (鹿) sounds like prosperity (禄) — an auspicious sign."},
    "fox":         {"label": "Fox (狐狸)",           "nums": ["0411","4110","1104","1041","4101"], "explanation": "Fox spirit is cunning and linked to mysterious fortunes."},
    "wolf":        {"label": "Wolf (狼)",            "nums": ["0425","4250","2504","5042","4205"], "explanation": "Wolf warns of a greedy rival nearby."},
    "leopard":     {"label": "Leopard (豹)",         "nums": ["0098","0980","9800","8009","0908"], "explanation": "Leopard is swifter than tiger — rapid unexpected gain."},
    "peacock":     {"label": "Peacock (孔雀)",       "nums": ["0123","1230","2301","3012","0312"], "explanation": "Peacock spreading tail feathers means showtime for luck."},
    "parrot":      {"label": "Parrot (鹦鹉)",        "nums": ["0207","2070","7002","0720","2007"], "explanation": "Parrot relays messages — news is coming."},
    # ── People ──
    "baby":        {"label": "Baby (婴儿)",          "nums": ["0031","0310","3100","1003","3010"], "explanation": "Baby in a dream signals new beginnings and small joys."},
    "infant":      {"label": "Baby (婴儿)",          "nums": ["0031","0310","3100","1003","3010"], "explanation": ""},
    "child":       {"label": "Child (小孩)",         "nums": ["0031","3100","1300","0130","3001"], "explanation": ""},
    "old man":     {"label": "Old Person (老人)",    "nums": ["0088","0880","8800","8008","8080"], "explanation": "Old man figure often represents an ancestor sending a blessing."},
    "elderly":     {"label": "Old Person (老人)",    "nums": ["0088","0880","8800","8008","8080"], "explanation": ""},
    "grandfather": {"label": "Old Person (老人)",    "nums": ["0088","0880","8800","8008","8080"], "explanation": ""},
    "grandmother": {"label": "Old Person (老人)",    "nums": ["0088","0880","8800","8008","8080"], "explanation": ""},
    "woman":       {"label": "Woman (女人)",         "nums": ["0069","0690","6900","9006","0609"], "explanation": ""},
    "lady":        {"label": "Woman (女人)",         "nums": ["0069","0690","6900","9006","0609"], "explanation": ""},
    "girl":        {"label": "Girl (女孩)",          "nums": ["0069","0690","6900","9006","0609"], "explanation": ""},
    "man":         {"label": "Man (男人)",           "nums": ["0168","1680","6801","8016","0618"], "explanation": ""},
    "ghost":       {"label": "Ghost (鬼)",           "nums": ["0023","0230","2300","3002","0302"], "explanation": "Ghost appearing in a dream is an ancestor's message."},
    "spirit":      {"label": "Ghost (鬼)",           "nums": ["0023","0230","2300","3002","0302"], "explanation": ""},
    "demon":       {"label": "Demon (恶鬼)",         "nums": ["0023","0230","2300","3002","0302"], "explanation": ""},
    "monk":        {"label": "Monk/Nun (僧尼)",      "nums": ["0047","0470","4700","7004","0407"], "explanation": "A monk or nun appearing signals spiritual guidance."},
    "nun":         {"label": "Monk/Nun (僧尼)",      "nums": ["0047","0470","4700","7004","0407"], "explanation": ""},
    "priest":      {"label": "Priest (神父)",        "nums": ["0047","0470","4700","7004","0407"], "explanation": ""},
    "police":      {"label": "Police (警察)",        "nums": ["0112","1120","1200","2011","1201"], "explanation": "Police in a dream warns of rules being broken or authority."},
    "soldier":     {"label": "Soldier (士兵)",       "nums": ["0065","0650","6500","5006","0605"], "explanation": "Soldier signals discipline and conflict ahead."},
    "thief":       {"label": "Thief (贼)",           "nums": ["0048","0480","4800","8004","0408"], "explanation": "Thief appearing means watch your valuables."},
    "robber":      {"label": "Robber (强盗)",        "nums": ["0048","0480","4800","8004","0408"], "explanation": ""},
    "burglar":     {"label": "Robber (强盗)",        "nums": ["0048","0480","4800","8004","0408"], "explanation": ""},
    "doctor":      {"label": "Doctor (医生)",        "nums": ["0034","0340","3400","4003","0304"], "explanation": "Doctor signals health concerns or recovery."},
    "teacher":     {"label": "Teacher (老师)",       "nums": ["0055","0550","5500","5005","5050"], "explanation": "Teacher represents wisdom and lessons learned."},
    "pregnant":    {"label": "Pregnancy (怀孕)",     "nums": ["0014","0140","1400","4001","1004"], "explanation": "Pregnancy is a strong positive omen for new beginnings."},
    "pregnancy":   {"label": "Pregnancy (怀孕)",     "nums": ["0014","0140","1400","4001","1004"], "explanation": ""},
    # ── Events / Situations ──
    "accident":    {"label": "Accident (车祸)",      "nums": ["0032","0320","3200","2003","0203"], "explanation": "Accident in a dream urges caution on the road."},
    "crash":       {"label": "Accident (车祸)",      "nums": ["0032","0320","3200","2003","0203"], "explanation": ""},
    "fire":        {"label": "Fire (火灾)",          "nums": ["0155","1550","5500","5055","1505"], "explanation": "Fire can destroy but also purify — a double-edged omen."},
    "burning":     {"label": "Fire (火灾)",          "nums": ["0155","1550","5500","5055","1505"], "explanation": ""},
    "flood":       {"label": "Flood (水灾)",         "nums": ["0038","0380","3800","8003","0308"], "explanation": "Flood of water can mean a flood of wealth or overwhelming loss."},
    "rain":        {"label": "Rain (下雨)",          "nums": ["0033","0330","3300","3003","3030"], "explanation": "Gentle rain in a dream signals prosperity flowing in."},
    "storm":       {"label": "Storm (风暴)",         "nums": ["0033","0330","3300","3003","3030"], "explanation": ""},
    "thunder":     {"label": "Thunder/Lightning (雷电)","nums":["0025","0250","2500","5002","0205"], "explanation": "Thunder wakes luck that has been sleeping."},
    "lightning":   {"label": "Thunder/Lightning (雷电)","nums":["0025","0250","2500","5002","0205"], "explanation": ""},
    "earthquake":  {"label": "Earthquake (地震)",    "nums": ["0036","0360","3600","6003","0603"], "explanation": "Earthquake shakes up the status quo — change is coming."},
    "wedding":     {"label": "Wedding (婚礼)",       "nums": ["0107","1070","7010","0710","1007"], "explanation": "Wedding is a highly auspicious event dream."},
    "marriage":    {"label": "Wedding (婚礼)",       "nums": ["0107","1070","7010","0710","1007"], "explanation": ""},
    "funeral":     {"label": "Funeral/Death (丧事)", "nums": ["0044","0440","4400","4004","4040"], "explanation": "Funeral dream may signal an ending that leads to new prosperity."},
    "death":       {"label": "Funeral/Death (丧事)", "nums": ["0044","0440","4400","4004","4040"], "explanation": ""},
    "fight":       {"label": "Fight (打架)",         "nums": ["0103","1030","3010","0301","1300"], "explanation": "Fight in a dream warns of conflict or competition."},
    "fighting":    {"label": "Fight (打架)",         "nums": ["0103","1030","3010","0301","1300"], "explanation": ""},
    "quarrel":     {"label": "Quarrel (吵架)",       "nums": ["0103","1030","3010","0301","1300"], "explanation": ""},
    "winning":     {"label": "Winning (赢)",         "nums": ["0777","7770","7007","7700","7077"], "explanation": "Dreaming of winning is a positive self-fulfilling omen."},
    "victory":     {"label": "Winning (赢)",         "nums": ["0777","7770","7007","7700","7077"], "explanation": ""},
    "lottery":     {"label": "Lottery Win (中奖)",   "nums": ["0777","7770","7007","7700","7077"], "explanation": ""},
    "flying":      {"label": "Flying (飞翔)",        "nums": ["0011","0110","1100","1001","1010"], "explanation": "Flying in a dream means ambitions will be achieved."},
    "falling":     {"label": "Falling (坠落)",       "nums": ["0022","0220","2200","2002","2020"], "explanation": "Falling signals a setback; take extra care."},
    "swimming":    {"label": "Swimming (游泳)",       "nums": ["0150","1500","5001","0015","5010"], "explanation": "Swimming with ease means navigating challenges well."},
    "running":     {"label": "Running (奔跑)",        "nums": ["0010","0100","1000","0001","1010"], "explanation": "Running fast signals urgent opportunity."},
    "chased":      {"label": "Being Chased (被追)",  "nums": ["0048","0480","4800","8004","0408"], "explanation": "Being chased means an opportunity is pressing you — act!"},
    "lost":        {"label": "Getting Lost (迷路)",  "nums": ["0052","0520","5200","2005","0502"], "explanation": "Getting lost signals confusion before clarity."},
    "treasure":    {"label": "Treasure (宝藏)",      "nums": ["0188","1880","8801","8018","1808"], "explanation": "Finding treasure is one of the best dream omens."},
    "money":       {"label": "Money (金钱)",         "nums": ["0168","1680","6801","8016","0618"], "explanation": "Money appearing in a dream signals financial gain."},
    "gold":        {"label": "Gold (黄金)",          "nums": ["0188","1880","8801","8018","1808"], "explanation": "Gold is the colour of heavenly luck."},
    "sick":        {"label": "Illness (生病)",        "nums": ["0034","0340","3400","4003","0304"], "explanation": "Dreaming of being sick warns to protect your health."},
    "illness":     {"label": "Illness (生病)",        "nums": ["0034","0340","3400","4003","0304"], "explanation": ""},
    "naked":       {"label": "Naked (裸体)",         "nums": ["0069","0690","6900","9006","0609"], "explanation": "Nakedness in a dream signals vulnerability but also honesty."},
    "crying":      {"label": "Crying (哭泣)",        "nums": ["0014","0140","1400","4001","1004"], "explanation": "Crying in a dream often signals joy coming soon."},
    "laughing":    {"label": "Laughing (大笑)",      "nums": ["0007","0070","0700","7000","7070"], "explanation": "Laughter in a dream is a happy omen."},
    # ── Objects / Nature ──
    "house":       {"label": "House/Home (房子)",    "nums": ["0348","3480","4803","8034","3048"], "explanation": "Home in a dream is your foundation of luck."},
    "home":        {"label": "House/Home (房子)",    "nums": ["0348","3480","4803","8034","3048"], "explanation": ""},
    "temple":      {"label": "Temple (庙)",          "nums": ["0471","4710","7104","1047","4701"], "explanation": "Visiting a temple in a dream means blessings received."},
    "hospital":    {"label": "Hospital (医院)",      "nums": ["0034","0340","3400","4003","0304"], "explanation": ""},
    "school":      {"label": "School (学校)",        "nums": ["0055","0550","5500","5005","5050"], "explanation": ""},
    "car":         {"label": "Car (车)",             "nums": ["0009","0090","9000","0900","9090"], "explanation": "Car signals a journey or opportunity approaching."},
    "vehicle":     {"label": "Car (车)",             "nums": ["0009","0090","9000","0900","9090"], "explanation": ""},
    "boat":        {"label": "Boat/Ship (船)",       "nums": ["0048","0480","4800","8004","0408"], "explanation": "Boat on calm water means smooth sailing ahead."},
    "ship":        {"label": "Boat/Ship (船)",       "nums": ["0048","0480","4800","8004","0408"], "explanation": ""},
    "airplane":    {"label": "Airplane (飞机)",      "nums": ["0011","0110","1100","1001","1010"], "explanation": "Airplane signals a distant opportunity or travel."},
    "plane":       {"label": "Airplane (飞机)",      "nums": ["0011","0110","1100","1001","1010"], "explanation": ""},
    "knife":       {"label": "Knife/Sword (刀剑)",   "nums": ["0061","0610","6100","1006","0601"], "explanation": "Knife signals cutting away the old to make way for new."},
    "sword":       {"label": "Knife/Sword (刀剑)",   "nums": ["0061","0610","6100","1006","0601"], "explanation": ""},
    "gun":         {"label": "Gun (枪)",             "nums": ["0062","0620","6200","2006","0602"], "explanation": "Gun signals sudden news or a shock coming."},
    "ring":        {"label": "Ring/Jewel (戒指)",    "nums": ["0171","1710","7101","1017","7110"], "explanation": "Ring symbolises completion and commitment."},
    "flower":      {"label": "Flower (花)",          "nums": ["0079","0790","7900","9007","0709"], "explanation": "Beautiful flowers signal blossoming fortune."},
    "rose":        {"label": "Flower (花)",          "nums": ["0079","0790","7900","9007","0709"], "explanation": ""},
    "tree":        {"label": "Tree (树)",            "nums": ["0034","0340","3400","4003","0304"], "explanation": "Tree roots signal stability; a fallen tree means upheaval."},
    "mountain":    {"label": "Mountain (山)",        "nums": ["0037","0370","3700","7003","0307"], "explanation": "Mountain symbolises a great obstacle or great achievement."},
    "river":       {"label": "River/Water (河水)",   "nums": ["0038","0380","3800","8003","0308"], "explanation": ""},
    "sea":         {"label": "Sea/Ocean (大海)",     "nums": ["0038","0380","3800","8003","0308"], "explanation": "Calm sea means wealth flowing; rough sea means stormy times."},
    "ocean":       {"label": "Sea/Ocean (大海)",     "nums": ["0038","0380","3800","8003","0308"], "explanation": ""},
    "sun":         {"label": "Sun (太阳)",           "nums": ["0001","0010","0100","1000","1010"], "explanation": "Bright sun signals a day of good fortune."},
    "moon":        {"label": "Moon (月亮)",          "nums": ["0002","0020","0200","2000","2002"], "explanation": "Full moon amplifies luck and romance."},
    "star":        {"label": "Star (星星)",          "nums": ["0002","0020","0200","2000","2002"], "explanation": "Stars signal guidance from above."},
    "blood":       {"label": "Blood (血液)",         "nums": ["0116","1160","6011","0611","1601"], "explanation": "Blood in a dream is a powerful omen of life force."},
    "teeth":       {"label": "Teeth/Tooth (牙齿)",   "nums": ["0041","0410","4100","1004","0401"], "explanation": "Losing teeth in a dream is a classic worry/loss sign."},
    "tooth":       {"label": "Teeth/Tooth (牙齿)",   "nums": ["0041","0410","4100","1004","0401"], "explanation": ""},
    "hair":        {"label": "Hair (头发)",          "nums": ["0003","0030","0300","3000","3003"], "explanation": "Hair falling out signals loss; thick hair means vitality."},
    "food":        {"label": "Food (食物)",          "nums": ["0018","0180","1800","8001","1080"], "explanation": "Abundant food means prosperity; lack means caution needed."},
    "rice":        {"label": "Rice (米饭)",          "nums": ["0018","0180","1800","8001","1080"], "explanation": "Rice is the staple of life — a sign of stable livelihood."},
    "egg":         {"label": "Egg (鸡蛋)",           "nums": ["0009","0090","9000","0900","9090"], "explanation": "Egg signals potential and new beginnings."},
    "excrement":   {"label": "Excrement (大便)",     "nums": ["0082","0820","8200","2008","0208"], "explanation": "Dreaming of excrement is paradoxically a sign of incoming wealth."},
    "poop":        {"label": "Excrement (大便)",     "nums": ["0082","0820","8200","2008","0208"], "explanation": ""},
    "toilet":      {"label": "Toilet (厕所)",        "nums": ["0082","0820","8200","2008","0208"], "explanation": ""},
    "coffin":      {"label": "Coffin (棺材)",        "nums": ["0044","0440","4400","4004","4040"], "explanation": "Coffin (棺) sounds like official (官) — may signal promotion."},
    "prison":      {"label": "Prison (监狱)",        "nums": ["0088","0880","8800","8008","8080"], "explanation": "Prison signals feeling trapped; a release is coming."},
    "prison bar":  {"label": "Prison (监狱)",        "nums": ["0088","0880","8800","8008","8080"], "explanation": ""},
}

PRIZE_ORDER = ["1st", "2nd", "3rd", "special", "consolation"]
PRIZE_LABEL = {
    "1st": "1st Prize",
    "2nd": "2nd Prize",
    "3rd": "3rd Prize",
    "special": "Special",
    "consolation": "Consolation",
}
LOTTERY_ORDER = ["damacai", "magnum", "toto"]
DRAW_DAYS = {2, 5, 6}  # Wednesday, Saturday, Sunday


def load_results() -> dict:
    if not os.path.exists(RESULTS_FILE):
        return {}
    with open(RESULTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def search_number(number: str, data: dict) -> list[dict]:
    matches = []
    for date_str in sorted(data.keys(), reverse=True):
        day = data[date_str]
        for key in LOTTERY_ORDER:
            lottery = day.get(key)
            if not lottery:
                continue
            prizes = lottery.get("prizes", {})
            for tier in PRIZE_ORDER:
                val = prizes.get(tier)
                hit = (val == number) if isinstance(val, str) else (number in (val or []))
                if hit:
                    matches.append({
                        "date": date_str,
                        "date_fmt": datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %d %b %Y"),
                        "lottery": lottery.get("label", key.upper()),
                        "draw_number": lottery.get("draw_number", ""),
                        "prize": PRIZE_LABEL[tier],
                        "tier": tier,
                    })
    return matches


def latest_draws(data: dict, n: int = 3) -> list[dict]:
    rows = []
    for date_str in sorted(data.keys(), reverse=True)[:n]:
        day = data[date_str]
        entry = {"date": date_str,
                 "date_fmt": datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %d %b %Y"),
                 "lotteries": []}
        for key in LOTTERY_ORDER:
            lot = day.get(key)
            if lot:
                entry["lotteries"].append({
                    "label": lot.get("label", key.upper()),
                    "draw_number": lot.get("draw_number", ""),
                    "prizes": lot.get("prizes", {}),
                })
        rows.append(entry)
    return rows


def compute_stats(data: dict, top: int = 20) -> tuple[dict, dict]:
    tiers = ["1st", "2nd", "3rd"]
    overall = {t: Counter() for t in tiers}
    by_lot  = {key: {t: Counter() for t in tiers} for key in LOTTERY_ORDER}

    for day in data.values():
        for key in LOTTERY_ORDER:
            lot = day.get(key)
            if not lot:
                continue
            prizes = lot.get("prizes", {})
            for t in tiers:
                val = prizes.get(t)
                if val:
                    overall[t][val] += 1
                    by_lot[key][t][val] += 1

    def top_n(counter):
        return counter.most_common(top)

    stats = {
        "all":     {t: top_n(overall[t])           for t in tiers},
        "damacai": {t: top_n(by_lot["damacai"][t]) for t in tiers},
        "magnum":  {t: top_n(by_lot["magnum"][t])  for t in tiers},
        "toto":    {t: top_n(by_lot["toto"][t])    for t in tiers},
    }
    counts = {t: sum(overall[t].values()) for t in tiers}
    return stats, counts


@app.route("/")
def index():
    data = load_results()
    recent = latest_draws(data)
    total_dates = len(data)
    return render_template("index.html", recent=recent, total_dates=total_dates, active_page="results")


def compute_extended_stats(data: dict, lottery: str | None = None) -> dict:
    today = datetime.today().date()
    tiers = ["1st", "2nd", "3rd"]
    keys = [lottery] if lottery else LOTTERY_ORDER

    pos_freq = [{str(d): 0 for d in range(10)} for _ in range(4)]
    sum_dist = Counter()
    balance  = Counter()
    patterns = Counter()
    quads    = set()
    last_seen: dict[str, str] = {}   # number → most recent date string

    for date_str in sorted(data.keys()):
        day = data[date_str]
        for key in keys:
            lot = day.get(key)
            if not lot:
                continue
            prizes = lot.get("prizes", {})
            for t in tiers:
                num = prizes.get(t)
                if not num or len(num) != 4 or not num.isdigit():
                    continue
                # Position frequency
                for i, d in enumerate(num):
                    pos_freq[i][d] += 1
                # Digit sum
                sum_dist[sum(int(d) for d in num)] += 1
                # Even/odd balance
                balance[sum(1 for d in num if int(d) % 2 == 0)] += 1
                # Repeat pattern
                unique = len(set(num))
                if unique == 4:
                    pat = "All Different"
                elif unique == 3:
                    pat = "One Pair"
                elif unique == 2:
                    pat = "Two Pairs" if max(Counter(num).values()) == 2 else "Three of a Kind"
                else:
                    pat = "Four of a Kind"
                    quads.add(num)
                patterns[pat] += 1
                # Hot / cold tracking
                last_seen[num] = date_str

    total = sum(sum_dist.values())

    # Normalise position freq to sorted list of (digit, count, pct)
    pos_freq_out = []
    for pos in range(4):
        pos_total = sum(pos_freq[pos].values())
        sorted_digits = sorted(pos_freq[pos].items(), key=lambda x: -x[1])
        pos_freq_out.append([
            {"digit": d, "count": c, "pct": round(c / pos_total * 100, 1) if pos_total else 0}
            for d, c in sorted_digits
        ])

    # Hot & Cold — compute days_ago from last_seen date
    hot = sorted(last_seen, key=last_seen.get, reverse=True)[:10]
    cold = sorted(last_seen, key=last_seen.get)[:10]
    def enrich(nums):
        out = []
        for n in nums:
            ds = last_seen[n]
            d = datetime.strptime(ds, "%Y-%m-%d").date()
            out.append({"num": n, "date": datetime.strptime(ds, "%Y-%m-%d").strftime("%d %b %Y"),
                        "days_ago": (today - d).days})
        return out

    # Digit sum: sorted list of [sum_val, count]
    sum_list = [[s, sum_dist[s]] for s in range(37)]
    sum_peak = max(sum_dist, key=sum_dist.get) if sum_dist else 18
    sum_max  = max(sum_dist.values()) if sum_dist else 1

    # Pattern breakdown with percentage
    pattern_order = ["All Different", "One Pair", "Two Pairs", "Three of a Kind", "Four of a Kind"]
    pattern_list = [(p, patterns[p], round(patterns[p] / total * 100, 1) if total else 0)
                    for p in pattern_order if p in patterns]

    # Balance labels
    balance_labels = {0: "All Odd", 1: "1 Even", 2: "2 Even", 3: "3 Even", 4: "All Even"}
    balance_list = [(balance_labels[k], balance[k], round(balance[k] / total * 100, 1) if total else 0)
                    for k in range(5)]

    return {
        "pos_freq":   pos_freq_out,
        "pos_total":  total,
        "hot":        enrich(hot),
        "cold":       enrich(cold),
        "sum_list":   sum_list,
        "sum_peak":   sum_peak,
        "sum_max":    sum_max,
        "balance":    balance_list,
        "patterns":   pattern_list,
        "quads":      sorted(quads),
        "total":      total,
    }


def next_draw_date() -> str:
    day = datetime.today() + timedelta(days=1)
    for _ in range(7):
        if day.weekday() in DRAW_DAYS:
            return day.strftime("%a, %d %b %Y")
        day += timedelta(days=1)
    return ""


def build_prediction_model(data: dict, lottery: str | None = None) -> dict:
    tiers = ["1st", "2nd", "3rd"]
    pos_counts = [{str(d): 0 for d in range(10)} for _ in range(4)]
    hist_counts: Counter = Counter()
    appearances: dict = defaultdict(list)
    keys = [lottery] if lottery else LOTTERY_ORDER

    for date_str in sorted(data.keys()):
        day = data[date_str]
        for key in keys:
            lot = day.get(key)
            if not lot:
                continue
            prizes = lot.get("prizes", {})
            for t in tiers:
                num = prizes.get(t)
                if num and len(num) == 4 and num.isdigit():
                    hist_counts[num] += 1
                    appearances[num].append(date_str)
                    for i, d in enumerate(num):
                        pos_counts[i][d] += 1

    pos_totals = [sum(pc.values()) for pc in pos_counts]
    pos_probs = [
        {d: (pos_counts[i][d] / pos_totals[i] if pos_totals[i] else 0.1)
         for d in "0123456789"}
        for i in range(4)
    ]

    today = datetime.today().date()
    last_seen: dict = {}
    avg_gap: dict = {}
    for num, dates in appearances.items():
        last_seen[num] = dates[-1]
        if len(dates) > 1:
            dts = [datetime.strptime(d, "%Y-%m-%d").date() for d in dates]
            gaps = [(dts[j + 1] - dts[j]).days for j in range(len(dts) - 1)]
            avg_gap[num] = sum(gaps) / len(gaps)

    total_days = (today - datetime.strptime(min(data.keys()), "%Y-%m-%d").date()).days
    global_avg_gap = total_days / max(len(hist_counts), 1)

    return {
        "pos_probs": pos_probs,
        "hist_counts": hist_counts,
        "hist_max": max(hist_counts.values()) if hist_counts else 1,
        "last_seen": last_seen,
        "avg_gap": avg_gap,
        "global_avg_gap": global_avg_gap,
        "today": today,
    }


def _colour(score_pct: float) -> tuple[str, str]:
    if score_pct >= 70:  return ("#f5c518", "Very High")
    if score_pct >= 50:  return ("#22c55e", "High")
    if score_pct >= 35:  return ("#06b6d4", "Above Average")
    if score_pct >= 20:  return ("#f59e0b", "Average")
    if score_pct >= 10:  return ("#f97316", "Below Average")
    return ("#64748b", "Low")


def score_number(num: str, model: dict) -> dict:
    pos_prob = 1.0
    for i, d in enumerate(num):
        pos_prob *= model["pos_probs"][i].get(d, 0.001)
    pos_norm = min(pos_prob / (0.1 ** 4), 2.5) / 2.5

    count = model["hist_counts"].get(num, 0)
    hist_norm = count / model["hist_max"]

    today = model["today"]
    if num in model["last_seen"]:
        last = datetime.strptime(model["last_seen"][num], "%Y-%m-%d").date()
        days = (today - last).days
        recency_norm = math.exp(-days / 365)
        last_seen_fmt = last.strftime("%d %b %Y")
    else:
        recency_norm = 0.05
        last_seen_fmt = "Never"
        days = None

    if num in model["avg_gap"] and model["avg_gap"][num]:
        days_since = (today - datetime.strptime(model["last_seen"][num], "%Y-%m-%d").date()).days
        gap_norm = min(days_since / model["avg_gap"][num], 3.0) / 3.0
    elif num in model["last_seen"]:
        days_since = (today - datetime.strptime(model["last_seen"][num], "%Y-%m-%d").date()).days
        gap_norm = min(days_since / model["global_avg_gap"], 3.0) / 3.0
    else:
        gap_norm = 0.4

    composite = 0.15 * pos_norm + 0.60 * hist_norm + 0.15 * recency_norm + 0.10 * gap_norm

    return {
        "num": num,
        "composite": round(composite, 6),
        "pos_norm": round(pos_norm * 100, 1),
        "hist_norm": round(hist_norm * 100, 1),
        "recency_norm": round(recency_norm * 100, 1),
        "gap_norm": round(gap_norm * 100, 1),
        "count": count,
        "last_seen_fmt": last_seen_fmt,
    }


def get_ranked_scores(model: dict) -> list[dict]:
    results = []
    for n in range(10000):
        num = f"{n:04d}"
        s = score_number(num, model)
        results.append(s)
    results.sort(key=lambda x: x["composite"], reverse=True)
    total = len(results)
    top_composite = results[0]["composite"] if results else 1
    for rank, r in enumerate(results, 1):
        percentile = round((1 - rank / total) * 100, 1)
        score_pct = round(r["composite"] / top_composite * 100, 1)
        colour, label = _colour(score_pct)
        r["rank"] = rank
        r["percentile"] = percentile
        r["score_pct"] = score_pct
        r["colour"] = colour
        r["label"] = label
    return results


LOTTERY_KEYS = {"all": None, "damacai": "damacai", "magnum": "magnum", "toto": "toto"}


@app.route("/predict")
def predict():
    data = load_results()
    top20s = {}
    for key, lot in LOTTERY_KEYS.items():
        model = build_prediction_model(data, lot)
        top20s[key] = get_ranked_scores(model)[:20]
    return render_template("predict.html", top20s=top20s, total_dates=len(data),
                           next_draw=next_draw_date(), active_page="predict")


@app.route("/api/score")
def api_score():
    number = request.args.get("number", "").strip()
    lottery = request.args.get("lottery", "all").strip()
    if not number.isdigit() or len(number) != 4:
        return jsonify({"error": "Enter a valid 4-digit number"}), 400
    if lottery not in LOTTERY_KEYS:
        lottery = "all"
    data = load_results()
    model = build_prediction_model(data, LOTTERY_KEYS[lottery])
    ranked = get_ranked_scores(model)
    rank_map = {r["num"]: r for r in ranked}
    return jsonify(rank_map[number])


@app.route("/analysis")
def analysis():
    data = load_results()
    stats, counts = compute_stats(data)
    exts = {k: compute_extended_stats(data, v) for k, v in LOTTERY_KEYS.items()}
    return render_template("analysis.html", stats=stats, counts=counts,
                           exts=exts, total_dates=len(data), active_page="analysis")


@app.route("/search")
def search():
    number = request.args.get("number", "").strip()
    if not number.isdigit() or len(number) != 4:
        return jsonify({"error": "Please enter a valid 4-digit number (0000–9999)."}), 400
    data = load_results()
    matches = search_number(number, data)
    return jsonify({
        "number": number,
        "matches": matches,
        "total_draws": len(data),
    })


@app.route("/simulate")
def simulate():
    return render_template("simulate.html", active_page="simulate",
                           next_draw=next_draw_date())




import requests as _req

_SB_URL = os.environ.get("SUPABASE_URL")
_SB_KEY = os.environ.get("SUPABASE_KEY")


def _sb_headers():
    return {"apikey": _SB_KEY, "Authorization": f"Bearer {_SB_KEY}",
            "Content-Type": "application/json"}


def _load_my_numbers() -> list:
    # Supabase (production)
    if _SB_URL and _SB_KEY:
        try:
            r = _req.get(f"{_SB_URL}/rest/v1/my_numbers_store?id=eq.1&select=data",
                         headers=_sb_headers(), timeout=5)
            rows = r.json()
            if rows:
                return json.loads(rows[0]["data"])
            return []
        except Exception:
            pass
    # Local file (development)
    if not os.path.exists(MY_NUMBERS_FILE):
        return []
    try:
        with open(MY_NUMBERS_FILE, encoding="utf-8") as f:
            content = f.read().strip()
            return json.loads(content) if content else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_my_numbers(data: list) -> None:
    # Supabase (production)
    if _SB_URL and _SB_KEY:
        try:
            _req.post(f"{_SB_URL}/rest/v1/my_numbers_store",
                      json={"id": 1, "data": json.dumps(data)},
                      headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates"},
                      timeout=5)
            return
        except Exception:
            pass
    # Local file (development)
    try:
        with open(MY_NUMBERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


@app.route("/api/my-numbers", methods=["GET"])
def api_my_numbers_get():
    return jsonify(_load_my_numbers())


@app.route("/api/my-numbers/add", methods=["POST"])
def api_my_numbers_add():
    body    = request.get_json(silent=True) or {}
    num     = body.get("num", "").strip()
    lottery = body.get("lottery", "all").strip()
    tries   = max(1, int(body.get("tries", 10)))
    date    = body.get("date", datetime.today().strftime("%Y-%m-%d"))

    if not num.isdigit() or len(num) != 4:
        return jsonify({"error": "Invalid number"}), 400
    if lottery not in LOTTERY_KEYS:
        lottery = "all"

    data = _load_my_numbers()
    if any(t["num"] == num and t["lottery"] == lottery for t in data):
        return jsonify({"error": "Already tracked"}), 409

    data.insert(0, {"num": num, "lottery": lottery, "tries": tries, "date": date})
    _save_my_numbers(data)
    return jsonify(data)


@app.route("/api/my-numbers/remove", methods=["POST"])
def api_my_numbers_remove():
    body    = request.get_json(silent=True) or {}
    num     = body.get("num", "").strip()
    lottery = body.get("lottery", "all").strip()
    date    = body.get("date", "")

    data = [t for t in _load_my_numbers()
            if not (t["num"] == num and t["lottery"] == lottery and t["date"] == date)]
    _save_my_numbers(data)
    return jsonify(data)


@app.route("/api/my-numbers/update", methods=["POST"])
def api_my_numbers_update():
    body        = request.get_json(silent=True) or {}
    key_num     = body.get("key_num", "").strip()
    key_lottery = body.get("key_lottery", "all").strip()
    key_date    = body.get("key_date", "").strip()
    new_lottery = body.get("lottery", key_lottery).strip()
    new_tries   = max(1, int(body.get("tries", 10)))

    if new_lottery not in LOTTERY_KEYS:
        new_lottery = "all"

    data = _load_my_numbers()
    for t in data:
        if t["num"] == key_num and t["lottery"] == key_lottery and t["date"] == key_date:
            t["lottery"] = new_lottery
            t["tries"]   = new_tries
    _save_my_numbers(data)
    return jsonify(data)


# ── Dream dictionary storage ──────────────────────────────────────────────────

_GEMINI_KEY = os.environ.get("GEMINI_API_KEY")


def _load_dream_dict() -> dict:
    raw = None
    if _SB_URL and _SB_KEY:
        try:
            r = _req.get(f"{_SB_URL}/rest/v1/dream_dict_store?id=eq.1&select=data",
                         headers=_sb_headers(), timeout=5)
            rows = r.json()
            if rows:
                raw = json.loads(rows[0]["data"])
        except Exception:
            pass
    if raw is None:
        try:
            if os.path.exists(DREAM_DICT_FILE):
                with open(DREAM_DICT_FILE, encoding="utf-8") as f:
                    raw = json.load(f)
        except Exception:
            pass
    if not raw:
        raw = dict(DREAM_SEED)
        _save_dream_dict(raw)
    return raw


def _save_dream_dict(d: dict) -> None:
    if _SB_URL and _SB_KEY:
        try:
            _req.post(f"{_SB_URL}/rest/v1/dream_dict_store",
                      json={"id": 1, "data": json.dumps(d, ensure_ascii=False)},
                      headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates"},
                      timeout=5)
            return
        except Exception:
            pass
    try:
        with open(DREAM_DICT_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def _normalise_phrase(text: str) -> str:
    return " ".join(text.lower().split())


def _match_dream(text: str, d: dict) -> dict | None:
    key = _normalise_phrase(text)
    entry = d.get(key)
    if entry:
        return {
            "label":       entry["label"],
            "nums":        entry["nums"],
            "cache_key":   key,
            "explanation": entry.get("explanation", ""),
        }
    return None


def _call_gemini(description: str) -> dict | None:
    if not _GEMINI_KEY:
        return None
    prompt = (
        'You are an expert in traditional Malaysian Chinese 4D lottery dream number '
        'associations (万字梦书 / dream book).\n'
        f'The user described: "{description}"\n\n'
        'What are the traditional 4D lucky numbers associated with this in the '
        'Malaysian Chinese dream book tradition? '
        'Respond ONLY with valid JSON (no markdown, no extra text):\n'
        '{"label":"Category in English (Chinese chars)","keywords":["kw1","kw2"],'
        '"nums":["XXXX","XXXX","XXXX","XXXX"],"explanation":"brief reason"}\n\n'
        'nums must be exactly 4-digit strings (zero-padded). Provide 4-5 numbers.'
    )
    try:
        r = _req.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash"
            f":generateContent?key={_GEMINI_KEY}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 512},
            },
            timeout=20,
        )
        if not r.ok:
            return None
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Strip markdown code fences if Gemini wraps anyway
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1][4:] if parts[1].startswith("json") else parts[1]
        result = json.loads(text.strip())
        if "label" not in result or "nums" not in result:
            return None
        result["nums"] = [
            str(n).zfill(4)[:4]
            for n in result["nums"]
            if str(n).replace(" ", "").isdigit()
        ]
        return result if result["nums"] else None
    except Exception:
        return None


@app.route("/dream")
def dream():
    return render_template("dream.html", active_page="dream", next_draw=next_draw_date())


@app.route("/api/dream", methods=["POST"])
def api_dream():
    body = request.get_json(silent=True) or {}
    description = body.get("description", "").strip()
    if not description:
        return jsonify({"error": "Please enter a description"}), 400

    d = _load_dream_dict()

    # Check phrase cache first — avoids calling Gemini for repeated queries
    match = _match_dream(description, d)
    if match:
        return jsonify({"source": "cache", **match})

    # Send the full phrase to Gemini
    if _GEMINI_KEY:
        result = _call_gemini(description)
        if result:
            phrase_key = _normalise_phrase(description)
            # Cache by the exact phrase
            d[phrase_key] = {
                "label":       result["label"],
                "nums":        result["nums"],
                "explanation": result.get("explanation", ""),
            }
            # Also cache by any short keywords Gemini returned (avoids repeat calls)
            for kw in result.get("keywords", []):
                kw_key = _normalise_phrase(kw)
                if kw_key and kw_key not in d:
                    d[kw_key] = {
                        "label":       result["label"],
                        "nums":        result["nums"],
                        "explanation": result.get("explanation", ""),
                    }
            _save_dream_dict(d)
            return jsonify({"source": "gemini", **result})
        return jsonify({"source": "none",
                        "message": "Gemini could not find a traditional 4D association for this."}), 200

    return jsonify({"source": "none",
                    "message": "No cached result found. Add GEMINI_API_KEY for AI lookup."}), 200


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
