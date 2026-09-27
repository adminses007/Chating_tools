/** i18n: 中文 / မြန်မာ */
window.I18N = (function () {
  const STORAGE_KEY = "chat_lang";

  const dict = {
    zh: {
      langName: "中文",
      subtitle: "简单、快速、像身边人一样随时聊",
      serverAddress: "服务器地址",
      testConnection: "测试连接",
      mobileHint: "手机浏览器打开：http://服务器IP:8000",
      login: "登录",
      register: "注册",
      username: "用户名",
      password: "密码",
      rememberUser: "记住用户名",
      rememberPass: "记住密码",
      enterChat: "进入聊天",
      displayName: "显示名称",
      loginPassword: "登录密码（至少 6 位）",
      inviteCode: "注册邀请码",
      inviteHint: "需要管理员提供的邀请码才能注册",
      createAccount: "创建账号",
      connectedHint: "已连接到本机 Server：{url}",
      contacts: "联系人",
      recentChats: "最近聊天",
      online: "在线",
      offline: "离线",
      startChatTitle: "开始一段对话",
      startChatDesc: "从左侧选择联系人或打开最近聊天",
      openChatList: "打开会话列表",
      back: "返回",
      newGroup: "新建群聊",
      theme: "主题",
      logout: "退出",
      typeMessage: "输入消息…",
      send: "发送",
      attach: "发送图片/视频/文件",
      download: "下载",
      leaveGroup: "退出群聊",
      groupMeta: "群聊 · {n} 位成员",
      noMessages: "暂无消息",
      image: "📷 图片",
      video: "🎬 视频",
      audio: "🎵 音频",
      file: "📎 文件",
      createGroup: "新建群聊",
      groupName: "群名称",
      cancel: "取消",
      create: "创建",
      connDisconnected: "未连接",
      connConnecting: "连接中…",
      connConnected: "已连接",
      connReconnecting: "重连中…",
      notConnected: "尚未连接服务器",
      downloadFail: "下载失败",
      uploadTimeout: "上传超时，请检查网络或减小文件",
      uploadNetwork: "上传失败（网络错误）",
      fileTooLarge: "文件过大（{size}）。服务器默认上限约 500MB。",
      openList: "打开会话列表",
      newMessage: "新消息",
      newMessageFrom: "{name} 发来新消息",
      newMessageBody: "{preview}",
    },
    my: {
      langName: "မြန်မာ",
      subtitle: "ရိုးရှင်း၊ မြန်ဆန်၊ အနီးအနားကသူများနဲ့ စကားပြောပါ",
      serverAddress: "ဆာဗာ လိပ်စာ",
      testConnection: "ချိတ်ဆက်မှု စစ်ဆေးရန်",
      mobileHint: "ဖုန်းဘရောက်ဇာဖြင့် ဖွင့်ပါ：http://ဆာဗာIP:8000",
      login: "အကောင့်ဝင်ရန်",
      register: "မှတ်ပုံတင်ရန်",
      username: "အသုံးပြုသူအမည်",
      password: "စကားဝှက်",
      rememberUser: "အသုံးပြုသူအမည် မှတ်ထားရန်",
      rememberPass: "စကားဝှက် မှတ်ထားရန်",
      enterChat: "စကားပြောရန်",
      displayName: "ပြသမည့်အမည်",
      loginPassword: "စကားဝှက် (အနည်းဆုံး ၆ လုံး)",
      inviteCode: "ဖိတ်ကြားကုဒ်",
      inviteHint: "မှတ်ပုံတင်ရန် အက်ဒ်မင် ဖိတ်ကြားကုဒ် လိုအပ်သည်",
      createAccount: "အကောင့် ဖန်တီးရန်",
      connectedHint: "ဆာဗာသို့ ချိတ်ဆက်ပြီး：{url}",
      contacts: "အဆက်အသွယ်များ",
      recentChats: "မကြာသေးမီ စကားပြောများ",
      online: "အွန်လိုင်း",
      offline: "အော့ဖ်လိုင်း",
      startChatTitle: "စကားပြော စတင်ပါ",
      startChatDesc: "ဘယ်ဘက်မှ အဆက်အသွယ် သို့မဟုတ် မကြာသေးမီ စကားပြောကို ရွေးပါ",
      openChatList: "စကားပြောစာရင်း ဖွင့်ရန်",
      back: "နောက်သို့",
      newGroup: "အုပ်စုအသစ်",
      theme: "အပြင်အဆင်",
      logout: "ထွက်ရန်",
      typeMessage: "မက်ဆေ့ချ် ရိုက်ထည့်ပါ…",
      send: "ပို့ရန်",
      attach: "ပုံ/ဗီဒီယို/ဖိုင် ပို့ရန်",
      download: "ဒေါင်းလုဒ်",
      leaveGroup: "အုပ်စုမှ ထွက်ရန်",
      groupMeta: "အုပ်စု · အဖွဲ့ဝင် {n} ဦး",
      noMessages: "မက်ဆေ့ချ် မရှိသေး",
      image: "📷 ပုံ",
      video: "🎬 ဗီဒီယို",
      audio: "🎵 အသံ",
      file: "📎 ဖိုင်",
      createGroup: "အုပ်စုအသစ်",
      groupName: "အုပ်စုအမည်",
      cancel: "ပယ်ဖျက်",
      create: "ဖန်တီးရန်",
      connDisconnected: "မချိတ်ဆက်ရသေး",
      connConnecting: "ချိတ်ဆက်နေသည်…",
      connConnected: "ချိတ်ဆက်ပြီး",
      connReconnecting: "ပြန်ချိတ်ဆက်နေသည်…",
      notConnected: "ဆာဗာ မချိတ်ဆက်ရသေး",
      downloadFail: "ဒေါင်းလုဒ် မအောင်မြင်ပါ",
      uploadTimeout: "တင်သွင်းချိန် ကုန်သွားသည်၊ ကွန်ရက် စစ်ပါ သို့မဟုတ် ဖိုင်လျှော့ပါ",
      uploadNetwork: "တင်သွင်းမှု မအောင်မြင် (ကွန်ရက် အမှား)",
      fileTooLarge: "ဖိုင်ကြီးလွန်းသည် ({size})။ ဆာဗာ ကန့်သတ်ချက် ၅၀၀MB ခန့်။",
      openList: "စကားပြောစာရင်း ဖွင့်ရန်",
      newMessage: "မက်ဆေ့ချ်အသစ်",
      newMessageFrom: "{name} ထံမှ မက်ဆေ့ချ်အသစ်",
      newMessageBody: "{preview}",
    },
  };

  let lang = localStorage.getItem(STORAGE_KEY) || "zh";
  if (!dict[lang]) lang = "zh";

  function t(key, vars) {
    const table = dict[lang] || dict.zh;
    let s = table[key] ?? dict.zh[key] ?? key;
    if (vars) {
      Object.keys(vars).forEach((k) => {
        s = s.replace(new RegExp(`\\{${k}\\}`, "g"), String(vars[k]));
      });
    }
    return s;
  }

  function apply() {
    document.documentElement.lang = lang === "my" ? "my" : "zh-CN";
    document.documentElement.setAttribute("data-lang", lang);
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      if (key) el.textContent = t(key);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      const key = el.getAttribute("data-i18n-placeholder");
      if (key) el.setAttribute("placeholder", t(key));
    });
    document.querySelectorAll("[data-i18n-title]").forEach((el) => {
      const key = el.getAttribute("data-i18n-title");
      if (key) el.setAttribute("title", t(key));
    });
    document.querySelectorAll("[data-i18n-aria]").forEach((el) => {
      const key = el.getAttribute("data-i18n-aria");
      if (key) el.setAttribute("aria-label", t(key));
    });
    document.querySelectorAll(".lang-switch button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.lang === lang);
    });
  }

  function setLang(next) {
    if (!dict[next]) return;
    lang = next;
    localStorage.setItem(STORAGE_KEY, lang);
    apply();
    window.dispatchEvent(new CustomEvent("langchange", { detail: { lang } }));
  }

  function getLang() {
    return lang;
  }

  return { t, apply, setLang, getLang, dict };
})();
