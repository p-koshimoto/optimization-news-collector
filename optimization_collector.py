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
import pytz

class OptimizationNewsCollector:
    def __init__(self):
        # 環境変数から設定を取得
        self.recipient_email = os.getenv('RECIPIENT_EMAIL')
        self.sender_email = os.getenv('SENDER_EMAIL')
        self.sender_password = os.getenv('GMAIL_APP_PASSWORD')
        self.discord_webhook = os.getenv('DISCORD_WEBHOOK')
        
        # 日本時間のタイムゾーン設定
        self.jst = pytz.timezone('Asia/Tokyo')
        
    def get_jst_time(self):
        """現在の日本時間を取得"""
        return datetime.now(self.jst)
    
    def collect_arxiv_papers(self, days_back=1):
        """arXivから数理最適化関連論文を収集"""
        print("📚 arXivから論文を収集中...")
        
        try:
            # より具体的な数理最適化関連のクエリ
            client = arxiv.Client()
            search = arxiv.Search(
                query=(
                    "cat:math.OC OR "
                    "(cat:cs.DM AND (ti:optimization OR ti:programming OR ti:algorithm)) OR "
                    "(cat:stat.ML AND ti:optimization) OR "
                    "ti:「linear programming」 OR ti:「integer programming」 OR "
                    "ti:「convex optimization」 OR ti:「nonlinear programming」 OR "
                    "ti:「combinatorial optimization」 OR ti:「stochastic optimization」"
                ),
                max_results=20,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending
            )
            
            papers = []
            cutoff_date = self.get_jst_time().date() - timedelta(days=days_back)
            
            for result in client.results(search):
                # 日本時間での日付比較
                published_jst = result.published.astimezone(self.jst).date()
                if published_jst >= cutoff_date:
                    papers.append({
                        'title': result.title.replace('\n', ' ').strip(),
                        'authors': [author.name for author in result.authors[:3]],
                        'abstract': result.summary.replace('\n', ' ').strip()[:500] + "...",
                        'url': result.entry_id,
                        'published': published_jst.strftime('%Y-%m-%d'),
                        'categories': result.categories
                    })
            
            print(f"✅ 論文 {len(papers)} 件を収集しました")
            return papers
            
        except Exception as e:
            print(f"❌ arXiv収集エラー: {e}")
            return []
    
    def collect_news_from_rss(self):
        """RSSから最適化関連ニュースを収集（フィルタリング強化）"""
        print("📰 ニュースを収集中...")
        
        # 数理最適化により関連性の高いRSSソース
        rss_urls = [
            "https://rss.cnn.com/rss/edition_technology.rss",
            "https://feeds.reuters.com/reuters/technologyNews",
            "https://rss.slashdot.org/Slashdot/slashdotMain",
            "https://feeds.feedburner.com/oreilly/radar"
        ]
        
        # より厳密なキーワードフィルタ
        optimization_keywords = [
            'optimization', 'optimisation', 'algorithm', 'programming',
            'linear programming', 'integer programming', 'convex',
            'machine learning', 'data science', 'operations research',
            'mathematical programming', 'solver', 'constraint',
            'heuristic', 'metaheuristic', 'genetic algorithm',
            'simulated annealing', 'particle swarm', 'gradient descent',
            'neural network', 'deep learning', 'reinforcement learning'
        ]
        
        # 除外キーワード（関連性の低いニュースを除外）
        exclude_keywords = [
            'celebrity', 'entertainment', 'sports', 'weather',
            'politics', 'election', 'crime', 'accident', 'war',
            'fashion', 'food', 'travel', 'celebrity', 'gossip'
        ]
        
        news_items = []
        for rss_url in rss_urls:
            try:
                feed = feedparser.parse(rss_url)
                for entry in feed.entries[:10]:  # 各RSSから10件チェック
                    title_lower = entry.title.lower()
                    summary_lower = getattr(entry, 'summary', '').lower()
                    combined_text = title_lower + ' ' + summary_lower
                    
                    # 除外キーワードチェック
                    if any(exclude in combined_text for exclude in exclude_keywords):
                        continue
                    
                    # 最適化関連キーワードでフィルタ（より厳密）
                    relevance_score = sum(1 for keyword in optimization_keywords 
                                        if keyword in combined_text)
                    
                    # 関連度スコアが2以上の記事のみ採用
                    if relevance_score >= 2:
                        # 日本時間で公開日を処理
                        published_date = getattr(entry, 'published', '')
                        if published_date:
                            try:
                                pub_dt = datetime.strptime(published_date[:19], '%Y-%m-%dT%H:%M:%S')
                                pub_dt = pytz.utc.localize(pub_dt).astimezone(self.jst)
                                published_jst = pub_dt.strftime('%Y-%m-%d %H:%M JST')
                            except:
                                published_jst = published_date
                        else:
                            published_jst = '日時不明'
                        
                        news_items.append({
                            'title': entry.title,
                            'link': entry.link,
                            'published': published_jst,
                            'summary': getattr(entry, 'summary', '')[:300] + "...",
                            'relevance_score': relevance_score
                        })
                        
                        # 十分な数の関連ニュースが集まったら終了
                        if len(news_items) >= 8:
                            break
                            
            except Exception as e:
                print(f"⚠️ RSS取得エラー ({rss_url}): {e}")
                continue
        
        # 関連度スコア順でソート
        news_items.sort(key=lambda x: x['relevance_score'], reverse=True)
        news_items = news_items[:5]  # 上位5件のみ
        
        print(f"✅ 関連ニュース {len(news_items)} 件を収集しました")
        return news_items
    
    def generate_simple_summary(self, text, max_sentences=2):
        """シンプルな要約生成（外部API不使用）"""
        sentences = text.split('.')
        summary_sentences = sentences[:max_sentences]
        return '. '.join(summary_sentences).strip() + '.'
    
    def generate_report(self, papers, news_items):
        """日本語レポートを生成（日本時間対応）"""
        jst_now = self.get_jst_time()
        
        report = f"""
# 🔬 数理最適化 日次レポート
**生成日時**: {jst_now.strftime('%Y年%m月%d日 %H:%M')} JST

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

## 📰 数理最適化関連技術ニュース ({len(news_items)}件)

"""
        
        if news_items:
            for i, news in enumerate(news_items, 1):
                report += f"""
### {i}. {news['title']}

- **要約**: {news['summary']}
- **関連度**: {'⭐' * news['relevance_score']}
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
- 生成時刻: {jst_now.strftime('%Y-%m-%d %H:%M:%S')} JST

---
*このレポートは自動生成されました (JST: Japan Standard Time)*
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
            jst_now = self.get_jst_time()
            msg['Subject'] = f"🔬 数理最適化レポート - {jst_now.strftime('%Y/%m/%d')} JST"
            
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
        """レポートをファイルに保存（日本時間でファイル名）"""
        jst_now = self.get_jst_time()
        filename = f"report_{jst_now.strftime('%Y%m%d_%H%M')}_JST.md"
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
        jst_now = self.get_jst_time()
        
        print("=" * 50)
        print(f"🚀 日次収集開始: {jst_now.strftime('%Y-%m-%d %H:%M:%S')} JST")
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
        print(f"  🕐 実行時刻: {jst_now.strftime('%Y-%m-%d %H:%M:%S')} JST")
        print("=" * 50)
        
        return {
            'papers_count': len(papers),
            'news_count': len(news_items),
            'email_sent': email_sent,
            'discord_sent': discord_sent,
            'execution_time_jst': jst_now.strftime('%Y-%m-%d %H:%M:%S JST')
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
