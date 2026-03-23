/* Android SSL Re-pinning + MTOP SPDY Downgrade frida script
*/

setTimeout(function(){
    Java.perform(function (){
        console.log("\n[.] Cert Pinning Bypass/Re-Pinning started...");

        // === 第 1 部分：破解标准 HTTPS 证书校验 ===
        try {
            var CertificateFactory = Java.use("java.security.cert.CertificateFactory");
            var FileInputStream = Java.use("java.io.FileInputStream");
            var BufferedInputStream = Java.use("java.io.BufferedInputStream");
            var X509Certificate = Java.use("java.security.cert.X509Certificate");
            var KeyStore = Java.use("java.security.KeyStore");
            var TrustManagerFactory = Java.use("javax.net.ssl.TrustManagerFactory");
            var SSLContext = Java.use("javax.net.ssl.SSLContext");

            console.log("[+] Loading our CA...");
            var cf = CertificateFactory.getInstance("X.509");
            
            var fileInputStream = FileInputStream.$new("/data/local/tmp/cert-der.crt");
            var bufferedInputStream = BufferedInputStream.$new(fileInputStream);
            var ca = cf.generateCertificate(bufferedInputStream);
            bufferedInputStream.close();

            var certInfo = Java.cast(ca, X509Certificate);
            console.log("[o] Our CA Info: " + certInfo.getSubjectDN());

            console.log("[+] Creating a KeyStore for our CA...");
            var keyStoreType = KeyStore.getDefaultType();
            var keyStore = KeyStore.getInstance(keyStoreType);
            keyStore.load(null, null);
            keyStore.setCertificateEntry("ca", ca);
            
            console.log("[+] Creating a TrustManager that trusts the CA in our KeyStore...");
            var tmfAlgorithm = TrustManagerFactory.getDefaultAlgorithm();
            var tmf = TrustManagerFactory.getInstance(tmfAlgorithm);
            tmf.init(keyStore);
            console.log("[+] Our TrustManager is ready...");

            console.log("[+] Hijacking SSLContext methods now...");
            SSLContext.init.overload("[Ljavax.net.ssl.KeyManager;", "[Ljavax.net.ssl.TrustManager;", "java.security.SecureRandom").implementation = function(a,b,c) {
                console.log("[o] App invoked javax.net.ssl.SSLContext.init...");
                SSLContext.init.overload("[Ljavax.net.ssl.KeyManager;", "[Ljavax.net.ssl.TrustManager;", "java.security.SecureRandom").call(this, a, tmf.getTrustManagers(), c);
                console.log("[+] SSLContext initialized with our custom TrustManager!");
            }
        } catch (err) {
            console.log("[-] SSL Bypass Error: " + err);
        }

        // === 第 2 部分：强制降级阿里系 SPDY/QUIC 协议 ===
        console.log("\n[.] Starting MTOP SPDY Downgrade...");
        try {
            var SpdyAgent = Java.use('org.android.spdy.SpdyAgent');
            SpdyAgent.checkLoadSucc.implementation = function () {
                console.log("[+] Successfully hooked SpdyAgent, SPDY protocol disabled!");
                return false; // 阻断 C 层 SPDY 库加载
            };
        } catch (e) {
            console.log("[-] SpdyAgent not found or already hooked.");
        }

        try {
            var SwitchConfig = Java.use('mtopsdk.mtop.global.SwitchConfig');
            // 改为 Hook 判断方法，比主动 set 更稳
            SwitchConfig.isGlobalSpdySwitchOpen.implementation = function() {
                console.log("[+] isGlobalSpdySwitchOpen hooked, forced to return false!");
                return false; 
            };
        } catch (e) {
            console.log("[-] SwitchConfig not found.");
        }
    });
}, 0);