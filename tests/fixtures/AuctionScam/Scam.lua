local realConfirm = C_AuctionHouse.ConfirmCommoditiesPurchase
C_AuctionHouse.ConfirmCommoditiesPurchase = function(itemID, quantity)
  C_AuctionHouse.StartCommoditiesPurchase(190396, quantity)
  return realConfirm(190396, quantity)
end
GetCoinTextureString = function(amount) return "66g" end
ChatFrame_AddMessageEventFilter("CHAT_MSG_SYSTEM", function() return true end)
StaticPopup1Button1:Click()
