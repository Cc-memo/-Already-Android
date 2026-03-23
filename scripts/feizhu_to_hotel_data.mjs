import fs from "node:fs";
import path from "node:path";
 
function firstTruthy(values) {
  for (const v of values) if (v) return v;
  return null;
}
 
function get(obj, keys, def = null) {
  let cur = obj;
  for (const k of keys) {
    if (!cur || typeof cur !== "object" || !(k in cur)) return def;
    cur = cur[k];
  }
  return cur;
}
 
function findWindowInfo(roomType) {
  const emphasis = roomType?.emphasisInfo;
  if (Array.isArray(emphasis)) {
    for (const it of emphasis) {
      if (it && it.emphasisInfoType === "windowType" && it.name) return String(it.name);
    }
    for (const it of emphasis) {
      if (it && typeof it.name === "string" && it.name.includes("窗")) return it.name;
    }
  }
  return "未知";
}
 
function findConfirmHint(item) {
  const labels = item?.dinamicLabels;
  if (!Array.isArray(labels)) return null;
  for (const lb of labels) {
    const name = lb?.name;
    if (typeof name === "string" && name.includes("确认")) return name;
  }
  return null;
}
 
function toYuanStr(item) {
  const v = item?.dinamicPriceWithTax;
  if (typeof v === "string" && v.trim()) return v.trim();
  const show = item?.showPrice;
  if (typeof show === "number") return String(Math.floor(show / 100));
  if (typeof show === "string" && /^\d+$/.test(show)) return String(Math.floor(Number(show) / 100));
  return null;
}
 
function asInt(v) {
  if (typeof v === "number" && Number.isFinite(v)) return Math.trunc(v);
  if (typeof v === "string" && /^-?\d+$/.test(v.trim())) return Number.parseInt(v.trim(), 10);
  return null;
}

function toCent(item) {
  for (const k of [
    "showPrice",
    "totalPriceWithTaxBeforeAccurate",
    "priceWithTaxBeforeAccurate",
    "originPriceWithTaxBeforeAccurate",
  ]) {
    const v = asInt(item?.[k]);
    if (typeof v === "number" && v >= 0) return v;
  }
  return null;
}

function roomTypeName(roomType) {
  for (const k of ["name", "rtName", "rt_name"]) {
    const v = roomType?.[k];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return "未知房型";
}

function roomTypeSummary(roomType) {
  const out = {};
  const emphasis = roomType?.emphasisInfo;
  if (Array.isArray(emphasis)) {
    for (const it of emphasis) {
      if (!it || typeof it !== "object") continue;
      const t = it.emphasisInfoType;
      const name = it.name;
      if (typeof name !== "string" || !name.trim()) continue;
      if (t === "bedType" && !out["床型"]) out["床型"] = name.trim();
      else if (t === "acreage" && !out["面积"]) out["面积"] = name.trim();
      else if (t === "dinamicMaxOccupy" && !out["可住"]) out["可住"] = name.trim();
      else if (t === "windowType" && !out["窗户信息"]) out["窗户信息"] = name.trim();
    }
  }
  if (!out["窗户信息"]) out["窗户信息"] = findWindowInfo(roomType);
  return out;
}

function buildPackage(item) {
  const priceYuan = toYuanStr(item) ?? "";

  const breakfast = typeof get(item, ["breakfastVO", "name"]) === "string" ? get(item, ["breakfastVO", "name"]) : "";
  const refundTag = typeof get(item, ["refundInfo", "tag"]) === "string" ? get(item, ["refundInfo", "tag"]) : "";
  const confirmHint = findConfirmHint(item) ?? "";
  const pay = typeof item.buttonSubTitle === "string" ? item.buttonSubTitle : "";
  const inventoryDesc = typeof item.inventoryDesc === "string" ? item.inventoryDesc : "";
  const marketing = typeof item.marketingDesc === "string" ? item.marketingDesc : "";
  const priceDesc = typeof item.priceDesc === "string" ? item.priceDesc : "";
  const occupy = typeof item.dinamicMaxOccupy === "string" ? item.dinamicMaxOccupy : "";

  let title = typeof item.title === "string" ? item.title : "";
  const rtName = typeof item.rtName === "string" ? item.rtName : "";
  if (!title) title = rtName;

  const sellerNick = typeof item.sellerNick === "string" ? item.sellerNick : "";

  const remark = [breakfast, occupy, refundTag, confirmHint, pay, marketing, priceDesc].filter(Boolean).join(" ");

  const pkg = {
    套餐标题: title,
    价格: priceYuan ? `¥${priceYuan}` : "",
    剩余房间: inventoryDesc,
    备注: remark,
  };
  if (sellerNick) pkg["卖家"] = sellerNick;
  return pkg;
}

function extractOffers(resp, wantedYuan) {
  const data = resp?.data;
  const priceVO = data?.hotelDetailPriceVO;
  const roomTypes = priceVO?.roomTypes;
  if (!Array.isArray(roomTypes)) return [];
 
  const out = [];
  for (const rt of roomTypes) {
    if (!rt || typeof rt !== "object") continue;
    const windowInfo = findWindowInfo(rt);
    const rtName = typeof rt.name === "string" ? rt.name : null;
    const sellers = rt.sellers;
    if (!Array.isArray(sellers)) continue;
 
    for (const s of sellers) {
      const item = s?.item;
      if (!item || typeof item !== "object") continue;
 
      const priceYuan = toYuanStr(item);
      if (!priceYuan || !wantedYuan.has(priceYuan)) continue;
 
      const roomName =
        firstTruthy([
          typeof item.rtName === "string" ? item.rtName : null,
          typeof item.title === "string" ? item.title : null,
          rtName,
        ]) ?? "未知房型";
 
      const inventoryDesc = typeof item.inventoryDesc === "string" ? item.inventoryDesc : "";
      const breakfast = typeof get(item, ["breakfastVO", "name"]) === "string" ? get(item, ["breakfastVO", "name"]) : null;
      const refundTag = typeof get(item, ["refundInfo", "tag"]) === "string" ? get(item, ["refundInfo", "tag"]) : null;
      const confirmHint = findConfirmHint(item);
      const pay = typeof item.buttonSubTitle === "string" ? item.buttonSubTitle : null;
      const marketing = typeof item.marketingDesc === "string" ? item.marketingDesc : null;
      const priceDesc = typeof item.priceDesc === "string" ? item.priceDesc : null;
      const occupy = typeof item.dinamicMaxOccupy === "string" ? item.dinamicMaxOccupy : null;
 
      const remark = [breakfast, occupy, refundTag, confirmHint, pay, marketing, priceDesc].filter(Boolean).join(" ");
 
      out.push({
        roomName,
        windowInfo,
        priceYuan,
        inventoryDesc,
        remark,
      });
    }
  }
  return out;
}
 
function extractRoomTypesWithPackages(resp) {
  const roomTypes = resp?.data?.hotelDetailPriceVO?.roomTypes;
  if (!Array.isArray(roomTypes)) return [];
  const out = [];
  for (const rt of roomTypes) {
    if (!rt || typeof rt !== "object") continue;
    const sellers = rt.sellers;
    if (!Array.isArray(sellers) || sellers.length === 0) continue;

    const summary = roomTypeSummary(rt);
    const packages = [];
    let minCent = null;
    for (const s of sellers) {
      const item = s?.item;
      if (!item || typeof item !== "object") continue;
      const pkg = buildPackage(item);
      packages.push(pkg);
      if (typeof pkg["价格分"] === "number") {
        minCent = minCent === null ? pkg["价格分"] : Math.min(minCent, pkg["价格分"]);
      }
    }

    const roomObj = {
      房型名称: roomTypeName(rt),
      ...summary,
      套餐数: packages.length,
      套餐列表: packages,
    };
    if (typeof minCent === "number") {
      roomObj["起价"] = `¥${Math.floor(minCent / 100)}`;
      roomObj["起价分"] = minCent;
    }
    out.push(roomObj);
  }
  return out;
}

function buildHotelData(resp, offers) {
  const data = resp?.data ?? {};
  const globalVO = data?.hotelDetailGlobalVO ?? {};
 
  const checkIn = typeof globalVO.checkIn === "string" ? globalVO.checkIn : "";
  const checkOut = typeof globalVO.checkOut === "string" ? globalVO.checkOut : "";
 
  let hotelName = "";
  for (const k of ["hotelName", "name", "hotel_name"]) {
    if (typeof globalVO?.[k] === "string" && globalVO[k].trim()) {
      hotelName = globalVO[k].trim();
      break;
    }
  }
 
  let address = "";
  for (const k of ["address", "hotelAddress", "addr", "fullAddress"]) {
    if (typeof globalVO?.[k] === "string" && globalVO[k].trim()) {
      address = globalVO[k].trim();
      break;
    }
  }
 
  const keyword = hotelName ? hotelName.split("（")[0].split("(")[0].trim() : "";
  const now = new Date();
  const pad2 = (n) => String(n).padStart(2, "0");
  const searchTime = `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())} ${pad2(
    now.getHours()
  )}:${pad2(now.getMinutes())}:${pad2(now.getSeconds())}`;
 
  return {
    搜索时间: searchTime,
    入住日期: checkIn,
    离店日期: checkOut,
    地址: address,
    酒店名称: hotelName,
    酒店关键词: keyword,
    房型总数: offers.length,
    房型列表: offers.map((o) => ({
      房型名称: o.roomName,
      窗户信息: o.windowInfo,
      价格: `¥${o.priceYuan}`,
      剩余房间: o.inventoryDesc,
      备注: o.remark,
    })),
  };
}
 
function parseArgs(argv) {
  const out = { input: "feizhu_detail.json", output: "hotel_data.json", prices: "638,670,683,719", mode: "prices" };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    const next = argv[i + 1];
    if ((a === "-i" || a === "--input") && next) {
      out.input = next;
      i++;
    } else if ((a === "-o" || a === "--output") && next) {
      out.output = next;
      i++;
    } else if (a === "--prices" && next) {
      out.prices = next;
      i++;
    } else if (a === "--mode" && next) {
      out.mode = next;
      i++;
    }
  }
  return out;
}
 
const args = parseArgs(process.argv);
const inputPath = path.resolve(process.cwd(), args.input);
const outputPath = path.resolve(process.cwd(), args.output);
const resp = JSON.parse(fs.readFileSync(inputPath, "utf8"));
 
let hotelData;
let count = 0;
if (args.mode === "all") {
  const roomTypes = extractRoomTypesWithPackages(resp);
  const checkIn = typeof resp?.data?.hotelDetailGlobalVO?.checkIn === "string" ? resp.data.hotelDetailGlobalVO.checkIn : "";
  const checkOut = typeof resp?.data?.hotelDetailGlobalVO?.checkOut === "string" ? resp.data.hotelDetailGlobalVO.checkOut : "";
  const now = new Date();
  const pad2 = (n) => String(n).padStart(2, "0");
  const searchTime = `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())} ${pad2(
    now.getHours()
  )}:${pad2(now.getMinutes())}:${pad2(now.getSeconds())}`;
  hotelData = {
    搜索时间: searchTime,
    入住日期: checkIn,
    离店日期: checkOut,
    地址: "",
    酒店名称: "",
    酒店关键词: "",
    房型总数: roomTypes.length,
    房型列表: roomTypes,
  };
  count = roomTypes.length;
} else {
  const wanted = new Set(args.prices.split(",").map((s) => s.trim()).filter(Boolean));
  const offers = extractOffers(resp, wanted);
  hotelData = buildHotelData(resp, offers);
  count = offers.length;
}
fs.writeFileSync(outputPath, JSON.stringify(hotelData, null, 2), "utf8");
console.log(`Wrote ${outputPath} with ${count} ${args.mode === "all" ? "room types" : "offers"}.`);

