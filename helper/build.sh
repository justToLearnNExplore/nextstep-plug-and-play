#!/usr/bin/env bash
# Builds helper/build/nextstep-box-helper.apk with the plain Android SDK tools (no Gradle).
# Needs: JDK 17+, Android SDK build-tools and one platform (android.jar).
# The signing key is made once, outside the repo, in ~/.nextstep-box/.
set -euo pipefail

cd "$(dirname "$0")"
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-/opt/homebrew/share/android-commandlinetools}}"
BT="$(ls -d "$SDK"/build-tools/* | sort -V | tail -1)"
JAR="$(ls -d "$SDK"/platforms/android-*/android.jar | sort -V | tail -1)"
VERSION="$(sed -n 's/.*static final int VERSION = \([0-9]*\);.*/\1/p' src/com/nextstepbox/helper/Box.java)"
KEYDIR="$HOME/.nextstep-box"
KS="$KEYDIR/helper-signing.p12"
PASS_FILE="$KEYDIR/helper-signing.pass"
OUT=build

rm -rf "$OUT" && mkdir -p "$OUT/classes" "$OUT/dex"

if [[ ! -f "$KS" ]]; then
  mkdir -p "$KEYDIR"
  (umask 077; openssl rand -hex 16 > "$PASS_FILE")
  keytool -genkeypair -keystore "$KS" -storetype PKCS12 -alias helper -keyalg RSA -keysize 2048 \
    -validity 10000 -dname "CN=NextStep Box helper" -storepass "$(cat "$PASS_FILE")" >/dev/null
  chmod 600 "$KS"
fi

"$BT/aapt2" link -o "$OUT/base.apk" -I "$JAR" --manifest AndroidManifest.xml \
  --min-sdk-version 26 --target-sdk-version 34 --version-code "$VERSION" --version-name "$VERSION"
javac -source 8 -target 8 -bootclasspath "$JAR" -Xlint:-options -d "$OUT/classes" $(find src -name '*.java')
(cd "$OUT/classes" && jar cf ../classes.jar .)
"$BT/d8" --release --min-api 26 --lib "$JAR" --output "$OUT/dex" "$OUT/classes.jar"
cp "$OUT/base.apk" "$OUT/unsigned.apk"
(cd "$OUT/dex" && zip -q -j ../unsigned.apk classes.dex)
"$BT/zipalign" -f -p 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"
"$BT/apksigner" sign --ks "$KS" --ks-pass "file:$PASS_FILE" --out "$OUT/nextstep-box-helper.apk" "$OUT/aligned.apk"
echo "built $OUT/nextstep-box-helper.apk (version $VERSION, $(wc -c < "$OUT/nextstep-box-helper.apk" | tr -d ' ') bytes)"
