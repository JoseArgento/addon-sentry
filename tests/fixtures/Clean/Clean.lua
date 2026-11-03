local template = [[ return function(a) return a + %d end ]]
local adder = loadstring(template:format(2))()
local GetSpellInfo = C_Spell.GetSpellInfo
print("Clean loaded", adder(1), "https://github.com/example/clean")
