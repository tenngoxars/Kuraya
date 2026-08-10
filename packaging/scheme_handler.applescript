-- Kuraya URL scheme 壳 app 的处理逻辑。
-- 由 build.sh 用 osacompile 编译成 Kuraya.app：
-- 浏览器点击 kuraya:<路径> 链接时系统唤起本 app，把 URL 转发给 kuraya play；
-- delete 动作也沿用同一入口。
-- 候选路径覆盖 brew（/opt/homebrew、/usr/local）与一键脚本（~/.local/bin）。
on open location u
	do shell script "for k in /opt/homebrew/bin/kuraya /usr/local/bin/kuraya \"$HOME/.local/bin/kuraya\"; do [ -x \"$k\" ] && exec \"$k\" play " & quoted form of u & "; done; exit 1"
end open location
