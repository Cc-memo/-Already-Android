/* 携程旅行专用：3秒延迟注入 + 反调试绕过 + HTTPS 证书解绑 
   使用方法：frida -U -f ctrip.android.view -l 此文件路径
*/

setTimeout(function(){
    Java.perform(function (){
        console.log("\n[***] 延迟 3 秒注入正式启动：避开启动检测高峰 [***]");

        // === 1. 反调试/代理环境检测深度绕过 ===
        try {
            var Debug = Java.use("android.os.Debug");
            Debug.isDebuggerConnected.implementation = function() {
                console.log("[+] 拦截到调试器检查：返回 false");
                return false;
            };
        } catch(e) { console.log("[-] Debug 检查 Hook 失败或类不存在"); }

        try {
            var System = Java.use("java.lang.System");
            System.getProperty.overload("java.lang.String").implementation = function(name) {
                // 携程会检查系统属性来判断是否挂了代理
                if (name == "http.proxyHost" || name == "http.proxyPort") {
                    console.log("[+] 拦截到代理属性检查: " + name + " -> 返回 null");
                    return null;
                }
                return this.getProperty(name);
            };
        } catch(e) { console.log("[-] Proxy 属性 Hook 失败"); }


        // === 2. 核心：HTTPS 证书解绑 (SSL Pinning Bypass) ===
        console.log("[.] 准备注入自定义 TrustManager...");
        try {
            var CertificateFactory = Java.use("java.security.cert.CertificateFactory");
            var FileInputStream = Java.use("java.io.FileInputStream");
            var BufferedInputStream = Java.use("java.io.BufferedInputStream");
            var KeyStore = Java.use("java.security.KeyStore");
            var TrustManagerFactory = Java.use("javax.net.ssl.TrustManagerFactory");
            var SSLContext = Java.use("javax.net.ssl.SSLContext");

            // 加载你推送到手机里的 Fiddler 证书
            var cf = CertificateFactory.getInstance("X.509");
            var fileInputStream = FileInputStream.$new("/data/local/tmp/cert-der.crt");
            var bufferedInputStream = BufferedInputStream.$new(fileInputStream);
            var ca = cf.generateCertificate(bufferedInputStream);
            bufferedInputStream.close();

            var keyStoreType = KeyStore.getDefaultType();
            var keyStore = KeyStore.getInstance(keyStoreType);
            keyStore.load(null, null);
            keyStore.setCertificateEntry("ca", ca);
            
            var tmfAlgorithm = TrustManagerFactory.getDefaultAlgorithm();
            var tmf = TrustManagerFactory.getInstance(tmfAlgorithm);
            tmf.init(keyStore);

            // Hook SSLContext.init，强制使用我们的 TrustManager
            SSLContext.init.overload("[Ljavax.net.ssl.KeyManager;", "[Ljavax.net.ssl.TrustManager;", "java.security.SecureRandom").implementation = function(a, b, c) {
                console.log("[o] 捕获到网络初始化请求，正在替换 TrustManager...");
                SSLContext.init.overload("[Ljavax.net.ssl.KeyManager;", "[Ljavax.net.ssl.TrustManager;", "java.security.SecureRandom").call(this, a, tmf.getTrustManagers(), c);
                console.log("[+] 替换成功：现在携程将信任 Fiddler 证书！");
            };
        } catch (err) {
            console.log("[-] SSL Bypass 核心逻辑异常: " + err);
        }

        // === 3. 辅助：协议降级逻辑 (防止它走非标准 HTTPS 通道) ===
        try {
            var SpdyAgent = Java.use('org.android.spdy.SpdyAgent');
            SpdyAgent.checkLoadSucc.implementation = function () {
                console.log("[+] 发现 SPDY 协议库，已强制关闭！");
                return false; 
            };
        } catch (e) {}

        console.log("\n[***] 脚本已全部加载完毕，请开始操作 App [***]\n");
    });
}, 10000); // 核心：延迟 3 秒