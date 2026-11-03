ProfilerDB = ProfilerDB or {}
local f = CreateFrame("Frame")
f:RegisterEvent("INSPECT_READY")
f:SetScript("OnEvent", function(_, _, guid)
  SetAchievementComparisonUnit("target")
  ProfilerDB[guid] = { gold = GetComparisonStatistic(328), name = UnitName("target") }
end)
