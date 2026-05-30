@echo off
if not exist ".\autowildcards" (
    echo This script must be run from the wildcards directory.
    pause
    exit /b
)

(
echo Jet Black
echo Charcoal
echo Graphite
echo Light Gray
echo Pure White
echo Ivory
echo Cream
echo Onyx
echo Silver
echo Slate
echo Alabaster
echo Eggshell
) > neutralcolors.txt

(
echo Chocolate Brown
echo Camel
echo Khaki
echo Beige
echo Taupe
echo Sand
echo Terracotta
echo Olive Green
echo Moss Green
echo Sienna
echo Umber
echo Stone
) > earthtonecolors.txt

(
echo Emerald
echo Sapphire
echo Ruby
echo Amethyst
echo Garnet
echo Topaz
echo Citrine
echo Tourmaline
echo Deep Teal
echo Aquamarine
echo Peridot
echo Lapis Lazuli
) > jeweltonecolors.txt

(
echo Baby Pink
echo Powder Blue
echo Mint Green
echo Lavender
echo Peach
echo Soft Yellow
echo Lilac
echo Periwinkle
echo Light Coral
echo Seafoam
echo Buttercup
echo Sky Blue
) > pastelcolors.txt

(
echo Fire Red
echo Cobalt Blue
echo Kelly Green
echo Canary Yellow
echo Hot Pink
echo Vibrant Orange
echo Magenta
echo Lime Green
echo Royal Blue
echo Scarlet
echo Tangerine
echo Chartreuse
) > brightcolors.txt

(
echo Dusty Rose
echo Slate Blue
echo Sage Green
echo Mustard
echo Burgundy
echo Burnt Orange
echo Teal
echo Plum
echo Mauve
echo Maroon
echo Forest Green
echo Midnight Blue
) > mutedcolors.txt

(
echo Gold
echo Silver
echo Copper
echo Bronze
echo Rose Gold
echo Platinum
echo Gunmetal
echo Pewter
echo Chrome
echo Brass
echo Titanium
echo Iridescent
) > metalliccolors.txt

(
echo Neon Green
echo Neon Pink
echo Neon Yellow
echo Neon Orange
echo Electric Blue
echo Shocking Pink
echo Electric Lime
echo Cyber Yellow
echo Blaze Orange
echo Proton Purple
echo Safety Green
echo Hot Coral
) > neoncolors.txt

echo All 8 color files have been created successfully.