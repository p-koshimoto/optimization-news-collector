import arxiv
import feedparser
import requests
from datetime import datetime, timedelta
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import sys

class OptimizationNewsCollector:
    def __init__(self):
        # 環境変数から設定を取得
        self.recipient_email = os.getenv('RECIPIENT_EMAIL')
        self.sender_email = os.getenv('SENDER_EMAIL')
        self.sender_password = os.getenv('GMAIL_APP_PASSWORD')
        self.discord_webhook = os.getenv('DISCORD_WEBHOOK')
        
    def collect_arxiv_papers(self, days_back=1):
        """arXivから数理最適化関連論文を収集"""
        print("📚 arXivから論文を収集中...")
        
        try:
            # 数理最適化関連のカテゴリで検索
            client = arxiv.Client()
            search = arxiv.Search(
                query="cat:math.OC OR cat:cs.DM OR ti:optimization OR ti:programming",
                max_results=20,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending
            )
            
            papers = []
            for result in client.results(search):
                # 過去N日以内の論文のみ
                if (datetime.now().date() - result.published.date()).days <= days_back:
                    papers.append({
                        'title': result.title.replace('\n', ' ').strip(),
                        'authors': [author.name for author in result.authors[:3]],  # 最初の3名
                        'abstract': result.summary.replace('\n', ' ').strip()[:500] + "...",
                        'url': result.entry_id,
                        'published': result.published.strftime('%Y-%m-%d'),
                        'categories': result.categories
                    })
            
            print(f"✅ 論文 {len(papers)} 件を収集しました")
            return papers
            
        except Exception as e:
            print(f"❌ arXiv収集エラー: {e}")
            return []
    
    def collect_news_from_rss(self):
        """RSSから最適化関連ニュースを収集"""
        print("📰 ニュースを収集中...")
        
        # 複数のRSSソースを使用
        rss_urls = [
            "https://rss.cnn.com/rss/edition.rss",
            "https://feeds.reuters.com/reuters/technologyNews",
            "https://rss.slashdot.org/Slashdot/slashdotMain"
        ]
        
        news_items = []
        for rss_url in rss_urls:
            try:
                feed = feedparser.parse(rss_url)
                for entry in feed.entries[:5]:  # 各RSSから5件
                    # 最適化関連キーワードでフィルタ
                    title_lower = entry.title.lower()
                    if any(keyword in title_lower for keyword in [
                        'optimization', 'algorithm', 'ai', 'machine learning', 
                        'data science', 'research'
                    ]):
                        news_items.append({
                            'title': entry.title,
                            'link': entry.link,
                            'published': getattr(entry, 'published', ''),
                            'summary': getattr(entry, 'summary', '')[:300] + "..."
                        })
            except Exception as e:
                print(f"⚠️ RSS取得エラー ({rss_url}): {e}")
                continue
        
        print(f"✅ ニュース {len(news_items)} 件を収集しました")
        return news_items
    
    def generate_simple_summary(self, text, max_sentences=2):
        """シンプルな要約生成（外部API不使用）"""
        sentences = text.split('.')
        # 最初の数文を要約として使用
        summary_sentences = sentences[:max_sentences]
        return '. '.join(summary_sentences).strip() + '.'
    
    def generate_report(self, papers, news_items):
        """日本語レポートを生成"""
        report = f"""
# 🔬 数理最適化 日次レポート
**生成日時**: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}

---

## 📚 新着論文 ({len(papers)}件)

"""
        
        if papers:
            for i, paper in enumerate(papers, 1):
                authors_str = ', '.join(paper['authors'])
                if len(paper['authors']) > 3:
                    authors_str += " 他"
                
                report += f"""
### {i}. {paper['title']}

- **著者**: {authors_str}
- **カテゴリ**: {', '.join(paper['categories'][:2])}
- **公開日**: {paper['published']}
- **概要**: {paper['abstract']}
- **URL**: {paper['url']}

---
"""
        else:
            report += "\n本日は新着論文がありませんでした。\n\n---\n"
        
        report += f"""

## 📰 関連技術ニュース ({len(news_items)}件)

"""
        
        if news_items:
            for i, news in enumerate(news_items, 1):
                report += f"""
### {i}. {news['title']}

- **要約**: {news['summary']}
- **リンク**: {news['link']}
- **公開日**: {news['published']}

---
"""
        else:
            report += "\n本日は関連ニュースがありませんでした。\n\n---\n"
        
        report += f"""

## 📊 収集統計
- 論文数: {len(papers)}件
- ニュース数: {len(news_items)}件
- 生成時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
*このレポートは自動生成されました*
"""
        
        return report
    
    def send_email_report(self, report):
        """Gmailでレポートを送信"""
        if not all([self.sender_email, self.sender_password, self.recipient_email]):
            print("❌ メール設定が不完全です")
            return False
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = self.recipient_email
            msg['Subject'] = f"🔬 数理最適化レポート - {datetime.now().strftime('%Y/%m/%d')}"
            
            msg.attach(MIMEText(report, 'plain', 'utf-8'))
            
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            text = msg.as_string()
            server.sendmail(self.sender_email, self.recipient_email, text)
            server.quit()
            
            print("✅ メールで送信完了")
            return True
            
        except Exception as e:
            print(f"❌ メール送信エラー: {e}")
            return False
    
    def send_discord_report(self, report):
        """Discord Webhookでレポートを送信"""
        if not self.discord_webhook:
            print("❌ Discord Webhook URLが設定されていません")
            return False
        
        try:
            # Discordの文字数制限（2000文字）対応
            if len(report) > 1900:
                report = report[:1900] + "\n\n[レポートが長いため切り詰められました]"
            
            payload = {
                "content": f"```markdown\n{report}\n```"
            }
            
            response = requests.post(self.discord_webhook, json=payload)
            if response.status_code == 204:
                print("✅ Discordに送信完了")
                return True
            else:
                print(f"❌ Discord送信エラー: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Discord送信エラー: {e}")
            return False
    
    def save_report_to_file(self, report):
        """レポートをファイルに保存"""
        filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"✅ レポートを {filename} に保存しました")
            return filename
        except Exception as e:
            print(f"❌ ファイル保存エラー: {e}")
            return None
    
    def run_daily_collection(self):
        """日次収集とレポート生成を実行"""
        print("=" * 50)
        print(f"🚀 日次収集開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 50)
        
        # データ収集
        papers = self.collect_arxiv_papers(days_back=2)  # 過去2日分
        news_items = self.collect_news_from_rss()
        
        # レポート生成
        report = self.generate_report(papers, news_items)
        
        # レポート保存
        self.save_report_to_file(report)
        
        # レポート送信
        email_sent = self.send_email_report(report)
        discord_sent = self.send_discord_report(report)
        
        print("=" * 50)
        print("📊 実行結果:")
        print(f"  📚 論文: {len(papers)}件")
        print(f"  📰 ニュース: {len(news_items)}件")
        print(f"  📧 メール送信: {'✅' if email_sent else '❌'}")
        print(f"  💬 Discord送信: {'✅' if discord_sent else '❌'}")
        print("=" * 50)
        
        return {
            'papers_count': len(papers),
            'news_count': len(news_items),
            'email_sent': email_sent,
            'discord_sent': discord_sent
        }

def main():
    """メイン実行関数"""
    print("🔬 数理最適化論文・ニュース収集システム")
    print("=" * 50)
    
    collector = OptimizationNewsCollector()
    result = collector.run_daily_collection()
    
    # 結果をJSONで出力（GitHub Actionsでの確認用）
    print("\n📄 実行結果（JSON）:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
