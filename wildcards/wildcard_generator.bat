@echo off
rem This is the DEFINITIVE, Probability-Corrected Keyword Generation System (v9.3).
rem This version fixes the probability bias by directly appending male color values to the female
rem color files, ensuring every color has an equal chance of being selected for the female subject.

setlocal enabledelayedexpansion

rem --- Create Directory and Timestamp Marker ---
if not exist .\autowildcards mkdir .\autowildcards
echo Directory 'autowildcards' is ready.
set "marker_file=.\autowildcards\unified_v9.3_verification_start.tmp"
(echo Verification timestamp)>"%marker_file%"

rem Prepare path for WMIC by escaping backslashes
set "wmic_path=%cd%\autowildcards"
set "wmic_path=%wmic_path:\=\\%"

rem Get the precise start time from the marker file
set "start_ts="
for /f "tokens=2 delims==" %%a in ('wmic datafile where "name='%wmic_path%\\unified_v9.3_verification_start.tmp'" get LastModified /value 2^>nul') do for /f %%b in ("%%a") do set "start_ts=%%b"

if not defined start_ts (
    echo ERROR: Could not get start timestamp. Verification cannot proceed.
    del "%marker_file%" >nul 2>&1
    pause
    exit /b
)

echo.
echo Generating DEFINITIVE Probability-Corrected (v9.3) Wildcard System files...

rem --- Generating TWO-TIER Color Palettes with Corrected Probability ---

rem -- NEUTRAL COLORS --
(echo Black)>.\autowildcards\neutral_colors_male.txt
(echo White)>>.\autowildcards\neutral_colors_male.txt
(echo Gray)>>.\autowildcards\neutral_colors_male.txt
(echo Charcoal)>>.\autowildcards\neutral_colors_male.txt
(echo Slate)>>.\autowildcards\neutral_colors_male.txt
(echo Stone)>>.\autowildcards\neutral_colors_male.txt
(echo Taupe)>>.\autowildcards\neutral_colors_male.txt
(echo Khaki)>>.\autowildcards\neutral_colors_male.txt
(echo Navy)>>.\autowildcards\neutral_colors_male.txt

(echo Ivory)>.\autowildcards\neutral_colors_female.txt
(echo Cream)>>.\autowildcards\neutral_colors_female.txt
(echo Beige)>>.\autowildcards\neutral_colors_female.txt
(echo Off-white)>>.\autowildcards\neutral_colors_female.txt
rem --- Appending male colors directly for equal probability ---
(echo Black)>>.\autowildcards\neutral_colors_female.txt
(echo White)>>.\autowildcards\neutral_colors_female.txt
(echo Gray)>>.\autowildcards\neutral_colors_female.txt
(echo Charcoal)>>.\autowildcards\neutral_colors_female.txt
(echo Slate)>>.\autowildcards\neutral_colors_female.txt
(echo Stone)>>.\autowildcards\neutral_colors_female.txt
(echo Taupe)>>.\autowildcards\neutral_colors_female.txt
(echo Khaki)>>.\autowildcards\neutral_colors_female.txt
(echo Navy)>>.\autowildcards\neutral_colors_female.txt

rem -- EARTHTONE COLORS --
(echo Olive green)>.\autowildcards\earthtone_colors_male.txt
(echo Moss green)>>.\autowildcards\earthtone_colors_male.txt
(echo Forest green)>>.\autowildcards\earthtone_colors_male.txt
(echo Chocolate brown)>>.\autowildcards\earthtone_colors_male.txt
(echo Umber)>>.\autowildcards\earthtone_colors_male.txt
(echo Mahogany)>>.\autowildcards\earthtone_colors_male.txt
(echo Clay)>>.\autowildcards\earthtone_colors_male.txt
(echo Sandstone)>>.\autowildcards\earthtone_colors_male.txt

(echo Terracotta)>.\autowildcards\earthtone_colors_female.txt
(echo Burnt sienna)>>.\autowildcards\earthtone_colors_female.txt
(echo Ochre)>>.\autowildcards\earthtone_colors_female.txt
(echo Rust)>>.\autowildcards\earthtone_colors_female.txt
(echo Sepia)>>.\autowildcards\earthtone_colors_female.txt
rem --- Appending male colors directly for equal probability ---
(echo Olive green)>>.\autowildcards\earthtone_colors_female.txt
(echo Moss green)>>.\autowildcards\earthtone_colors_female.txt
(echo Forest green)>>.\autowildcards\earthtone_colors_female.txt
(echo Chocolate brown)>>.\autowildcards\earthtone_colors_female.txt
(echo Umber)>>.\autowildcards\earthtone_colors_female.txt
(echo Mahogany)>>.\autowildcards\earthtone_colors_female.txt
(echo Clay)>>.\autowildcards\earthtone_colors_female.txt
(echo Sandstone)>>.\autowildcards\earthtone_colors_female.txt

rem -- JEWELTONE COLORS --
(echo Sapphire blue)>.\autowildcards\jeweltone_colors_male.txt
(echo Emerald green)>>.\autowildcards\jeweltone_colors_male.txt
(echo Ruby red)>>.\autowildcards\jeweltone_colors_male.txt
(echo Garnet)>>.\autowildcards\jeweltone_colors_male.txt
(echo Aquamarine)>>.\autowildcards\jeweltone_colors_male.txt
(echo Tanzanite)>>.\autowildcards\jeweltone_colors_male.txt
(echo Maroon)>>.\autowildcards\jeweltone_colors_male.txt

(echo Amethyst purple)>.\autowildcards\jeweltone_colors_female.txt
(echo Tourmaline pink)>>.\autowildcards\jeweltone_colors_female.txt
(echo Deep magenta)>>.\autowildcards\jeweltone_colors_female.txt
(echo Citrine orange)>>.\autowildcards\jeweltone_colors_female.txt
(echo Topaz yellow)>>.\autowildcards\jeweltone_colors_female.txt
(echo Peridot)>>.\autowildcards\jeweltone_colors_female.txt
rem --- Appending male colors directly for equal probability ---
(echo Sapphire blue)>>.\autowildcards\jeweltone_colors_female.txt
(echo Emerald green)>>.\autowildcards\jeweltone_colors_female.txt
(echo Ruby red)>>.\autowildcards\jeweltone_colors_female.txt
(echo Garnet)>>.\autowildcards\jeweltone_colors_female.txt
(echo Aquamarine)>>.\autowildcards\jeweltone_colors_female.txt
(echo Tanzanite)>>.\autowildcards\jeweltone_colors_female.txt
(echo Maroon)>>.\autowildcards\jeweltone_colors_female.txt

rem -- PASTEL COLORS --
(echo Baby blue)>.\autowildcards\pastel_colors_male.txt
(echo Mint green)>>.\autowildcards\pastel_colors_male.txt
(echo Pale yellow)>>.\autowildcards\pastel_colors_male.txt
(echo Seafoam green)>>.\autowildcards\pastel_colors_male.txt
(echo Cornflower blue)>>.\autowildcards\pastel_colors_male.txt
(echo Light coral)>>.\autowildcards\pastel_colors_male.txt

(echo Lavender)>.\autowildcards\pastel_colors_female.txt
(echo Peach)>>.\autowildcards\pastel_colors_female.txt
(echo Light pink)>>.\autowildcards\pastel_colors_female.txt
(echo Soft lilac)>>.\autowildcards\pastel_colors_female.txt
(echo Periwinkle)>>.\autowildcards\pastel_colors_female.txt
(echo Powder pink)>>.\autowildcards\pastel_colors_female.txt
(echo Blush pink)>>.\autowildcards\pastel_colors_female.txt
rem --- Appending male colors directly for equal probability ---
(echo Baby blue)>>.\autowildcards\pastel_colors_female.txt
(echo Mint green)>>.\autowildcards\pastel_colors_female.txt
(echo Pale yellow)>>.\autowildcards\pastel_colors_female.txt
(echo Seafoam green)>>.\autowildcards\pastel_colors_female.txt
(echo Cornflower blue)>>.\autowildcards\pastel_colors_female.txt
(echo Light coral)>>.\autowildcards\pastel_colors_female.txt

rem -- BRIGHT COLORS --
(echo Electric blue)>.\autowildcards\bright_colors_male.txt
(echo Vibrant orange)>>.\autowildcards\bright_colors_male.txt
(echo Sunshine yellow)>>.\autowildcards\bright_colors_male.txt
(echo Fiery red)>>.\autowildcards\bright_colors_male.txt
(echo Bright turquoise)>>.\autowildcards\bright_colors_male.txt
(echo Lime green)>>.\autowildcards\bright_colors_male.txt
(echo Scarlet)>>.\autowildcards\bright_colors_male.txt
(echo Canary yellow)>>.\autowildcards\bright_colors_male.txt

(echo Hot pink)>.\autowildcards\bright_colors_female.txt
(echo Fuchsia)>>.\autowildcards\bright_colors_female.txt
(echo Bold purple)>>.\autowildcards\bright_colors_female.txt
(echo Chartreuse)>>.\autowildcards\bright_colors_female.txt
(echo Magenta)>>.\autowildcards\bright_colors_female.txt
rem --- Appending male colors directly for equal probability ---
(echo Electric blue)>>.\autowildcards\bright_colors_female.txt
(echo Vibrant orange)>>.\autowildcards\bright_colors_female.txt
(echo Sunshine yellow)>>.\autowildcards\bright_colors_female.txt
(echo Fiery red)>>.\autowildcards\bright_colors_female.txt
(echo Bright turquoise)>>.\autowildcards\bright_colors_female.txt
(echo Lime green)>>.\autowildcards\bright_colors_female.txt
(echo Scarlet)>>.\autowildcards\bright_colors_female.txt
(echo Canary yellow)>>.\autowildcards\bright_colors_female.txt

rem -- MUTED COLORS --
(echo Slate blue)>.\autowildcards\muted_colors_male.txt
(echo Heather gray)>>.\autowildcards\muted_colors_male.txt
(echo Teal)>>.\autowildcards\muted_colors_male.txt
(echo Faded denim)>>.\autowildcards\muted_colors_male.txt
(echo Burnt orange)>>.\autowildcards\muted_colors_male.txt
(echo Olive)>>.\autowildcards\muted_colors_male.txt
(echo Sage green)>>.\autowildcards\muted_colors_male.txt
(echo Muted mustard)>>.\autowildcards\muted_colors_male.txt

(echo Dusty rose)>.\autowildcards\muted_colors_female.txt
(echo Plum)>>.\autowildcards\muted_colors_female.txt
(echo Mauve)>>.\autowildcards\muted_colors_female.txt
(echo Antique gold)>>.\autowildcards\muted_colors_female.txt
(echo Fig)>>.\autowildcards\muted_colors_female.txt
rem --- Appending male colors directly for equal probability ---
(echo Slate blue)>>.\autowildcards\muted_colors_female.txt
(echo Heather gray)>>.\autowildcards\muted_colors_female.txt
(echo Teal)>>.\autowildcards\muted_colors_female.txt
(echo Faded denim)>>.\autowildcards\muted_colors_female.txt
(echo Burnt orange)>>.\autowildcards\muted_colors_female.txt
(echo Olive)>>.\autowildcards\muted_colors_female.txt
(echo Sage green)>>.\autowildcards\muted_colors_female.txt
(echo Muted mustard)>>.\autowildcards\muted_colors_female.txt

rem -- METALLIC COLORS --
(echo Gold)>.\autowildcards\metallic_colors_male.txt
(echo Silver)>>.\autowildcards\metallic_colors_male.txt
(echo Bronze)>>.\autowildcards\metallic_colors_male.txt
(echo Pewter)>>.\autowildcards\metallic_colors_male.txt
(echo Gunmetal)>>.\autowildcards\metallic_colors_male.txt
(echo Platinum)>>.\autowildcards\metallic_colors_male.txt
(echo Brass)>>.\autowildcards\metallic_colors_male.txt
(echo Chrome)>>.\autowildcards\metallic_colors_male.txt
(echo Titanium)>>.\autowildcards\metallic_colors_male.txt

(echo Copper)>.\autowildcards\metallic_colors_female.txt
(echo Rose gold)>>.\autowildcards\metallic_colors_female.txt
(echo Iridescent)>>.\autowildcards\metallic_colors_female.txt
rem --- Appending male colors directly for equal probability ---
(echo Gold)>>.\autowildcards\metallic_colors_female.txt
(echo Silver)>>.\autowildcards\metallic_colors_female.txt
(echo Bronze)>>.\autowildcards\metallic_colors_female.txt
(echo Pewter)>>.\autowildcards\metallic_colors_female.txt
(echo Gunmetal)>>.\autowildcards\metallic_colors_female.txt
(echo Platinum)>>.\autowildcards\metallic_colors_female.txt
(echo Brass)>>.\autowildcards\metallic_colors_female.txt
(echo Chrome)>>.\autowildcards\metallic_colors_female.txt
(echo Titanium)>>.\autowildcards\metallic_colors_female.txt

rem -- NEON COLORS --
(echo Neon green)>.\autowildcards\neon_colors_male.txt
(echo Neon yellow)>>.\autowildcards\neon_colors_male.txt
(echo Electric lime)>>.\autowildcards\neon_colors_male.txt
(echo Cyber blue)>>.\autowildcards\neon_colors_male.txt
(echo Laser red)>>.\autowildcards\neon_colors_male.txt
(echo Acid green)>>.\autowildcards\neon_colors_male.txt
(echo Neon orange)>>.\autowildcards\neon_colors_male.txt
(echo Volt yellow)>>.\autowildcards\neon_colors_male.txt

(echo Neon pink)>.\autowildcards\neon_colors_female.txt
(echo Hot magenta)>>.\autowildcards\neon_colors_female.txt
(echo Shocking pink)>>.\autowildcards\neon_colors_female.txt
(echo Fluorescent green)>>.\autowildcards\neon_colors_female.txt
rem --- Appending male colors directly for equal probability ---
(echo Neon green)>>.\autowildcards\neon_colors_female.txt
(echo Neon yellow)>>.\autowildcards\neon_colors_female.txt
(echo Electric lime)>>.\autowildcards\neon_colors_female.txt
(echo Cyber blue)>>.\autowildcards\neon_colors_female.txt
(echo Laser red)>>.\autowildcards\neon_colors_female.txt
(echo Acid green)>>.\autowildcards\neon_colors_female.txt
(echo Neon orange)>>.\autowildcards\neon_colors_female.txt
(echo Volt yellow)>>.\autowildcards\neon_colors_female.txt


rem --- Generating Final "ALL COLORS" Aggregators ---
(echo __neutral_colors_male__)>.\autowildcards\all_colors_male.txt
(echo __earthtone_colors_male__)>>.\autowildcards\all_colors_male.txt
(echo __jeweltone_colors_male__)>>.\autowildcards\all_colors_male.txt
(echo __pastel_colors_male__)>>.\autowildcards\all_colors_male.txt
(echo __bright_colors_male__)>>.\autowildcards\all_colors_male.txt
(echo __muted_colors_male__)>>.\autowildcards\all_colors_male.txt
(echo __metallic_colors_male__)>>.\autowildcards\all_colors_male.txt
(echo __neon_colors_male__)>>.\autowildcards\all_colors_male.txt

(echo __neutral_colors_female__)>.\autowildcards\all_colors_female.txt
(echo __earthtone_colors_female__)>>.\autowildcards\all_colors_female.txt
(echo __jeweltone_colors_female__)>>.\autowildcards\all_colors_female.txt
(echo __pastel_colors_female__)>>.\autowildcards\all_colors_female.txt
(echo __bright_colors_female__)>>.\autowildcards\all_colors_female.txt
(echo __muted_colors_female__)>>.\autowildcards\all_colors_female.txt
(echo __metallic_colors_female__)>>.\autowildcards\all_colors_female.txt
(echo __neon_colors_female__)>>.\autowildcards\all_colors_female.txt

rem --- The rest of the script remains the same as it correctly uses the new color files ---

rem --- RE-ARCHITECTED FEMALE Keyword Component Files ---
(echo a beautiful woman, hourglass physique, slim waist, ^(sensual cleavage:1.1^) highlighting huge natural breasts, long wavy black hair with slight curls)>.\autowildcards\subject_female.txt
(echo traditional wear, Kanjeevaram saree, __jeweltone_colors_female__, __metallic_colors_female__, fabric: silk)>.\autowildcards\female_traditional_outfit.txt
(echo traditional wear, Anarkali suit, __earthtone_colors_female__, fabric: silk)>>.\autowildcards\female_traditional_outfit.txt
(echo traditional wear, Ghagra Choli, __bright_colors_female__, __metallic_colors_female__, fabric: silk)>>.\autowildcards\female_traditional_outfit.txt
(echo traditional wear, Salwar Kameez, __pastel_colors_female__, fabric: cotton)>>.\autowildcards\female_traditional_outfit.txt
(echo traditional wear, Bandhani saree, __muted_colors_female__, fabric: silk)>>.\autowildcards\female_traditional_outfit.txt
(echo traditional wear, half-saree, __bright_colors_female__, fabric: silk)>>.\autowildcards\female_traditional_outfit.txt
(echo traditional wear, Banarasi lehenga, __metallic_colors_female__, __jeweltone_colors_female__, fabric: silk)>>.\autowildcards\female_traditional_outfit.txt
(echo traditional wear, cotton saree, __muted_colors_female__, fabric: cotton)>>.\autowildcards\female_traditional_outfit.txt
(echo formal wear, evening gown, __jeweltone_colors_female__, fabric: silk)>.\autowildcards\female_formal_outfit.txt
(echo formal wear, pantsuit, __neutral_colors_female__, fabric: crepe)>>.\autowildcards\female_formal_outfit.txt
(echo formal wear, cocktail dress, __metallic_colors_female__, fabric: satin)>>.\autowildcards\female_formal_outfit.txt
(echo formal wear, mermaid-style dress, __muted_colors_female__, fabric: velvet)>>.\autowildcards\female_formal_outfit.txt
(echo formal wear, velvet gown, __jeweltone_colors_female__, fabric: velvet)>>.\autowildcards\female_formal_outfit.txt
(echo formal wear, A-line dress, __pastel_colors_female__, fabric: satin)>>.\autowildcards\female_formal_outfit.txt
(echo formal wear, Little Black Dress, Black, fabric: crepe)>>.\autowildcards\female_formal_outfit.txt
(echo formal wear, sequined gown, __metallic_colors_female__, fabric: sequined)>>.\autowildcards\female_formal_outfit.txt
(echo casual wear, high-waisted jeans, crop top, __neutral_colors_female__, fabric: denim)>.\autowildcards\female_casual_outfit.txt
(echo casual wear, floral sundress, __pastel_colors_female__, fabric: cotton)>>.\autowildcards\female_casual_outfit.txt
(echo casual wear, Kurti with leggings, __earthtone_colors_female__, fabric: cotton)>>.\autowildcards\female_casual_outfit.txt
(echo casual wear, tank top, denim mini-skirt, __bright_colors_female__, fabric: denim)>>.\autowildcards\female_casual_outfit.txt
(echo casual wear, oversized sweater, __muted_colors_female__, fabric: wool)>>.\autowildcards\female_casual_outfit.txt
(echo casual wear, athletic leggings, sports top, __neon_colors_female__, fabric: lycra)>>.\autowildcards\female_casual_outfit.txt
(echo casual wear, button-down shirt, linen pants, __neutral_colors_female__, fabric: linen)>>.\autowildcards\female_casual_outfit.txt
(echo casual wear, jumpsuit, __earthtone_colors_female__, fabric: cotton)>>.\autowildcards\female_casual_outfit.txt
(echo athletic wear, performance t-shirt and track pants, __bright_colors_female__, __neutral_colors_female__)>.\autowildcards\female_athletic_outfit.txt
(echo athletic wear, full tracksuit, __muted_colors_female__, __neon_colors_female__,)>>.\autowildcards\female_athletic_outfit.txt
(echo active wear, fleece pullover, __earthtone_colors_female__)>>.\autowildcards\female_athletic_outfit.txt
(echo athletic wear, sports jersey, __bright_colors_female__)>>.\autowildcards\female_athletic_outfit.txt
(echo athleisure wear, stylish hoodie with joggers, __muted_colors_female__, __neutral_colors_female__)>>.\autowildcards\female_athletic_outfit.txt
(echo athletic wear, yoga top and comfortable pants, __pastel_colors_female__, __neutral_colors_female__)>>.\autowildcards\female_athletic_outfit.txt
(echo active wear, running jacket, __neon_colors_female__)>>.\autowildcards\female_athletic_outfit.txt
(echo athletic wear, tennis dress, __pastel_colors_female__, White)>>.\autowildcards\female_athletic_outfit.txt
(echo swimwear, one-piece swimsuit, __bright_colors_female__, fabric: lycra)>.\autowildcards\female_swimwear_outfit.txt
(echo swimwear, string bikini, __metallic_colors_female__, fabric: lycra)>>.\autowildcards\female_swimwear_outfit.txt
(echo swimwear, high-waisted bikini, __pastel_colors_female__, fabric: lycra)>>.\autowildcards\female_swimwear_outfit.txt
(echo swimwear, monokini with cutouts, __neon_colors_female__, fabric: lycra)>>.\autowildcards\female_swimwear_outfit.txt
(echo swimwear, sporty bikini, __neutral_colors_female__, fabric: lycra)>>.\autowildcards\female_swimwear_outfit.txt
(echo swimwear, crochet bikini, __earthtone_colors_female__, fabric: crochet)>>.\autowildcards\female_swimwear_outfit.txt
(echo swimwear, animal print bikini, __earthtone_colors_female__, fabric: lycra)>>.\autowildcards\female_swimwear_outfit.txt
(echo lingerie, lace teddy, __jeweltone_colors_female__, fabric: lace)>.\autowildcards\female_lingerie_outfit.txt
(echo lingerie, silk babydoll, __pastel_colors_female__, fabric: silk)>>.\autowildcards\female_lingerie_outfit.txt
(echo lingerie, matching lace bra and panties, __neutral_colors_female__, fabric: lace)>>.\autowildcards\female_lingerie_outfit.txt
(echo lingerie, satin corset, __metallic_colors_female__, fabric: satin)>>.\autowildcards\female_lingerie_outfit.txt
(echo lingerie, sheer chiffon chemise, __pastel_colors_female__, fabric: chiffon)>>.\autowildcards\female_lingerie_outfit.txt
(echo lingerie, leather-like bustier, Black, fabric: faux leather)>>.\autowildcards\female_lingerie_outfit.txt
(echo lingerie, sheer bodysuit, __neutral_colors_female__, fabric: mesh)>>.\autowildcards\female_lingerie_outfit.txt
(echo costume, fantasy, ancient Indian queen, __jeweltone_colors_female__, __metallic_colors_female__)>.\autowildcards\female_costume_outfit.txt
(echo costume, sci-fi, rebel princess, __neutral_colors_female__)>>.\autowildcards\female_costume_outfit.txt
(echo costume, gothic, vampire countess, __jeweltone_colors_female__)>>.\autowildcards\female_costume_outfit.txt
(echo costume, fantasy, forest nymph, __earthtone_colors_female__)>>.\autowildcards\female_costume_outfit.txt
(echo costume, cyberpunk, hacker, __neon_colors_female__)>>.\autowildcards\female_costume_outfit.txt
(echo costume, fantasy, celestial goddess, __metallic_colors_female__, __pastel_colors_female__)>>.\autowildcards\female_costume_outfit.txt
(echo costume, fantasy, sorceress, __jeweltone_colors_female__)>>.\autowildcards\female_costume_outfit.txt
(echo costume, historical, pirate captain, __earthtone_colors_female__)>>.\autowildcards\female_costume_outfit.txt
(echo __female_traditional_outfit__)>.\autowildcards\female_outfit_category.txt
(echo __female_formal_outfit__)>>.\autowildcards\female_outfit_category.txt
(echo __female_casual_outfit__)>>.\autowildcards\female_outfit_category.txt
(echo __female_athletic_outfit__)>>.\autowildcards\female_outfit_category.txt
(echo __female_swimwear_outfit__)>>.\autowildcards\female_outfit_category.txt
(echo __female_lingerie_outfit__)>>.\autowildcards\female_outfit_category.txt
(echo __female_costume_outfit__)>>.\autowildcards\female_outfit_category.txt

rem --- RE-ARCHITECTED MALE Keyword Component Files ---
(echo a handsome 27-year-old Telugu man, dark brown eyes, stylish hair, thick ducktail beard trimmed perfectly, muscular physique)>.\autowildcards\subject_male.txt
(echo traditional wear, embroidered Sherwani, __jeweltone_colors_male__, __metallic_colors_male__, fabric: silk)>.\autowildcards\male_traditional_outfit.txt
(echo traditional wear, Dhoti with Angavastram, __neutral_colors_male__, __metallic_colors_male__, fabric: silk)>>.\autowildcards\male_traditional_outfit.txt
(echo traditional wear, Jodhpuri Bandhgala Suit, __muted_colors_male__, __neutral_colors_male__, fabric: wool)>>.\autowildcards\male_traditional_outfit.txt
(echo traditional wear, Linen Kurta with Pajama, __earthtone_colors_male__, __pastel_colors_male__, fabric: linen)>>.\autowildcards\male_traditional_outfit.txt
(echo traditional wear, Nehru Jacket over Kurta, __jeweltone_colors_male__, __neutral_colors_male__, fabric: velvet)>>.\autowildcards\male_traditional_outfit.txt
(echo traditional wear, Pathani Suit, __neutral_colors_male__, __earthtone_colors_male__, fabric: cotton)>>.\autowildcards\male_traditional_outfit.txt
(echo traditional wear, Chikankari Angarkha, __pastel_colors_male__, fabric: cotton)>>.\autowildcards\male_traditional_outfit.txt
(echo traditional wear, block-printed Kurta, __bright_colors_male__, __neutral_colors_male__, fabric: cotton)>>.\autowildcards\male_traditional_outfit.txt
(echo formal wear, classic Black Tuxedo, White, fabric: satin)>.\autowildcards\male_formal_outfit.txt
(echo formal wear, three-piece suit, __neutral_colors_male__, fabric: wool)>>.\autowildcards\male_formal_outfit.txt
(echo formal wear, velvet blazer, __jeweltone_colors_male__, __neutral_colors_male__, fabric: velvet)>>.\autowildcards\male_formal_outfit.txt
(echo formal wear, white dinner jacket, White, Black, fabric: silk)>>.\autowildcards\male_formal_outfit.txt
(echo formal wear, pinstripe suit, __neutral_colors_male__, fabric: wool)>>.\autowildcards\male_formal_outfit.txt
(echo formal wear, double-breasted suit, __muted_colors_male__, fabric: wool)>>.\autowildcards\male_formal_outfit.txt
(echo formal wear, two-piece business suit, __neutral_colors_male__, fabric: wool)>>.\autowildcards\male_formal_outfit.txt
(echo formal wear, tweed blazer, __earthtone_colors_male__, fabric: tweed)>>.\autowildcards\male_formal_outfit.txt
(echo semi-formal, dress shirt and trousers, __pastel_colors_male__, __neutral_colors_male__, fabric: cotton)>>.\autowildcards\male_formal_outfit.txt
(echo semi-formal, sports blazer with chinos, __muted_colors_male__, __neutral_colors_male__, fabric: linen)>>.\autowildcards\male_formal_outfit.txt
(echo semi-formal, linen suit, __pastel_colors_male__, __neutral_colors_male__, fabric: linen)>>.\autowildcards\male_formal_outfit.txt
(echo semi-formal, Bundhgala shirt ^(Nehru collar^), __muted_colors_male__, fabric: cotton)>>.\autowildcards\male_formal_outfit.txt
(echo casual wear, slim-fit jeans and t-shirt, __muted_colors_male__, fabric: denim)>.\autowildcards\male_casual_outfit.txt
(echo casual wear, polo shirt with chinos, __pastel_colors_male__, __neutral_colors_male__, fabric: cotton)>>.\autowildcards\male_casual_outfit.txt
(echo casual wear, denim jacket, __neutral_colors_male__, fabric: denim)>>.\autowildcards\male_casual_outfit.txt
(echo casual wear, plaid flannel shirt, __muted_colors_male__, __earthtone_colors_male__, fabric: flannel)>>.\autowildcards\male_casual_outfit.txt
(echo casual wear, rugged leather jacket, __earthtone_colors_male__, __neutral_colors_male__, fabric: leather)>>.\autowildcards\male_casual_outfit.txt
(echo casual wear, stylish bomber jacket, __muted_colors_male__, __bright_colors_male__, fabric: satin)>>.\autowildcards\male_casual_outfit.txt
(echo casual wear, hoodie and joggers set, __muted_colors_male__, __neutral_colors_male__, fabric: fleece)>>.\autowildcards\male_casual_outfit.txt
(echo casual wear, short cotton Kurta with jeans, __earthtone_colors_male__, __pastel_colors_male__, fabric: cotton)>>.\autowildcards\male_casual_outfit.txt
(echo casual wear, linen shirt with shorts, __pastel_colors_male__, __neutral_colors_male__, fabric: linen)>>.\autowildcards\male_casual_outfit.txt
(echo casual wear, cable-knit sweater, __muted_colors_male__, fabric: wool)>>.\autowildcards\male_casual_outfit.txt
(echo casual wear, block-printed button-down shirt, __earthtone_colors_male__, __bright_colors_male__, fabric: cotton)>>.\autowildcards\male_casual_outfit.txt
(echo casual wear, cargo pants, __earthtone_colors_male__, fabric: canvas)>>.\autowildcards\male_casual_outfit.txt
(echo athletic wear, performance t-shirt, __bright_colors_male__, __neutral_colors_male__, fabric: polyester)>.\autowildcards\male_athletic_outfit.txt
(echo athletic wear, full tracksuit, __muted_colors_male__, __neon_colors_male__, fabric: nylon)>>.\autowildcards\male_athletic_outfit.txt
(echo active wear, fleece pullover, __earthtone_colors_male__, fabric: fleece)>>.\autowildcards\male_athletic_outfit.txt
(echo athletic wear, Indian cricket team jersey, Blue, __bright_colors_male__, fabric: polyester)>>.\autowildcards\male_athletic_outfit.txt
(echo athleisure wear, stylish hoodie with joggers, __muted_colors_male__, __neutral_colors_male__, fabric: fleece)>>.\autowildcards\male_athletic_outfit.txt
(echo active wear, long-sleeve performance shirt, __neutral_colors_male__, __neon_colors_male__, fabric: polyester)>>.\autowildcards\male_athletic_outfit.txt
(echo athletic wear, warm-up jacket, __muted_colors_male__, __bright_colors_male__, fabric: nylon)>>.\autowildcards\male_athletic_outfit.txt
(echo active wear, yoga kurta, __pastel_colors_male__, __neutral_colors_male__, fabric: cotton)>>.\autowildcards\male_athletic_outfit.txt
(echo costume, dc comics, Tactical Batsuit, Black, Gray, unmasked)>.\autowildcards\male_costume_outfit.txt
(echo costume, dc comics, Classic Superman Suit, Blue, Red, Yellow)>>.\autowildcards\male_costume_outfit.txt
(echo costume, dc comics, The Joker, __jeweltone_colors_male__, __bright_colors_male__)>>.\autowildcards\male_costume_outfit.txt
(echo costume, dc comics, Green Lantern, Green, Black, unmasked)>>.\autowildcards\male_costume_outfit.txt
(echo costume, dc comics, John Constantine, __earthtone_colors_male__, __neutral_colors_male__)>>.\autowildcards\male_costume_outfit.txt
(echo costume, dc comics, Green Arrow, __earthtone_colors_male__, hood down)>>.\autowildcards\male_costume_outfit.txt
(echo costume, marvel comics, Star-Lord's Ravager Outfit, __jeweltone_colors_male__, __earthtone_colors_male__, unmasked)>>.\autowildcards\male_costume_outfit.txt
(echo costume, marvel comics, Captain America Suit, __bright_colors_male__, __neutral_colors_male__, unhelmeted)>>.\autowildcards\male_costume_outfit.txt
(echo costume, marvel comics, Doctor Strange, __jeweltone_colors_male__)>>.\autowildcards\male_costume_outfit.txt
(echo costume, marvel comics, Asgardian Armor ^(Thor^), __metallic_colors_male__, __jeweltone_colors_male__, unhelmeted)>>.\autowildcards\male_costume_outfit.txt
(echo costume, marvel comics, The Punisher's Tactical Gear, Black, White)>>.\autowildcards\male_costume_outfit.txt
(echo costume, marvel comics, Wolverine's X-Men Uniform, __bright_colors_male__, __jeweltone_colors_male__, unmasked)>>.\autowildcards\male_costume_outfit.txt
(echo costume, star wars, Jedi Master Robes, __earthtone_colors_male__, __neutral_colors_male__)>>.\autowildcards\male_costume_outfit.txt
(echo costume, star wars, Sith Acolyte Robes, Black, Red, unmasked)>>.\autowildcards\male_costume_outfit.txt
(echo costume, star wars, Bounty Hunter's Attire, __earthtone_colors_male__, unhelmeted)>>.\autowildcards\male_costume_outfit.txt
(echo costume, star wars, Imperial Officer Uniform, Black, Gray)>>.\autowildcards\male_costume_outfit.txt
(echo costume, star wars, Rebel Alliance Pilot, __bright_colors_male__, White, helmet held)>>.\autowildcards\male_costume_outfit.txt
(echo costume, star wars, Smuggler's Outfit, __neutral_colors_male__)>>.\autowildcards\male_costume_outfit.txt
(echo costume, warhammer 40k, Imperial Commissar, Black, Red, Gold)>>.\autowildcards\male_costume_outfit.txt
(echo costume, warhammer 40k, Imperial Guardsman, Khaki, Green, unhelmeted)>>.\autowildcards\male_costume_outfit.txt
(echo costume, warhammer 40k, Chaos Cultist Leader, Black, Red, unmasked)>>.\autowildcards\male_costume_outfit.txt
(echo costume, warhammer 40k, Rogue Trader, __jeweltone_colors_male__, __metallic_colors_male__)>>.\autowildcards\male_costume_outfit.txt
(echo costume, warhammer 40k, Inquisitor, Black, Red)>>.\autowildcards\male_costume_outfit.txt
(echo costume, gaming, Renaissance Assassin, White, Red, hood down)>>.\autowildcards\male_costume_outfit.txt
(echo costume, gaming, Witcher's Kaer Morhen Armor, Black, Brown)>>.\autowildcards\male_costume_outfit.txt
(echo costume, gaming, Cyberpunk Mercenary, Black, __neon_colors_male__)>>.\autowildcards\male_costume_outfit.txt
(echo costume, gaming, SOLDIER 1st Class, Purple, Black)>>.\autowildcards\male_costume_outfit.txt
(echo costume, gaming, Knight of the Erdtree, __metallic_colors_male__, unhelmeted)>>.\autowildcards\male_costume_outfit.txt
(echo costume, gaming, S.T.A.R.S. Operative, __jeweltone_colors_male__, Black)>>.\autowildcards\male_costume_outfit.txt
(echo costume, gaming, God of War ^(Kratos-style^), Red, Brown, spartan)>>.\autowildcards\male_costume_outfit.txt
(echo costume, gaming, Sneaking Suit ^(Solid Snake-style^), __muted_colors_male__)>>.\autowildcards\male_costume_outfit.txt
(echo costume, noir, Detective, __neutral_colors_male__, fedora hat)>>.\autowildcards\male_costume_outfit.txt

(echo __male_traditional_outfit__)>.\autowildcards\male_outfit_category.txt
(echo __male_formal_outfit__)>>.\autowildcards\male_outfit_category.txt
(echo __male_casual_outfit__)>>.\autowildcards\male_outfit_category.txt
(echo __male_athletic_outfit__)>>.\autowildcards\male_outfit_category.txt
(echo __male_costume_outfit__)>>.\autowildcards\male_outfit_category.txt

rem --- Generating Final Keyword Package Assemblers ---
(echo __subject_female__, __female_outfit_category__)>.\autowildcards\female_scene.txt
(echo __subject_male__, __male_outfit_category__)>.\autowildcards\male_scene.txt

echo.
echo All definitive, gender-curated wildcard files have been generated.
echo.

rem --- Verification System ---
echo Verifying all files...
set verified_count=0
set failed_files=

set "file_list=neutral_colors_male.txt neutral_colors_female.txt earthtone_colors_male.txt earthtone_colors_female.txt jeweltone_colors_male.txt jeweltone_colors_female.txt pastel_colors_male.txt pastel_colors_female.txt bright_colors_male.txt bright_colors_female.txt muted_colors_male.txt muted_colors_female.txt metallic_colors_male.txt metallic_colors_female.txt neon_colors_male.txt neon_colors_female.txt all_colors_male.txt all_colors_female.txt subject_female.txt female_traditional_outfit.txt female_formal_outfit.txt female_casual_outfit.txt female_athletic_outfit.txt female_swimwear_outfit.txt female_lingerie_outfit.txt female_costume_outfit.txt female_outfit_category.txt subject_male.txt male_traditional_outfit.txt male_formal_outfit.txt male_casual_outfit.txt male_athletic_outfit.txt male_costume_outfit.txt male_outfit_category.txt female_scene.txt male_scene.txt"

set /a num_files=0
for %%f in (%file_list%) do set /a num_files+=1

for %%f in (%file_list%) do (
    set "file_ts="
    for /f "tokens=2 delims==" %%a in ('wmic datafile where "name='!wmic_path!\\%%f'" get LastModified /value 2^>nul') do for /f %%b in ("%%a") do set "file_ts=%%b"
    
    if defined file_ts (
        if "!file_ts!" geq "!start_ts!" (
            set /a verified_count+=1
        ) else (
            set failed_files=!failed_files! %%f
        )
    ) else (
        set failed_files=!failed_files! %%f
    )
)

if exist "%marker_file%" del "%marker_file%"

if %verified_count% equ %num_files% (
    echo.
    echo SUCCESS: All %num_files% required files were created or updated successfully.
) else (
    echo.
    echo ERROR: Verification failed. Found %verified_count% of %num_files% new or updated files.
    echo The following files were NOT updated or are missing:!failed_files!
)

echo.
echo This window will close in 5 seconds...
timeout /t 5 >nul
endlocal