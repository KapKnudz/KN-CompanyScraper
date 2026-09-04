class AnalysisEngine:

    def __init__(self, skills):
        self.skills = skills

    def analyze(self, company):

        results = {}

        for skill in self.skills:
            results[skill.name] = skill.run(company)

        return results

    def analyze_companies(self, companies):
        """Analyze only the explicitly supplied companies, preserving their order."""
        return {
            company.id: self.analyze(company)
            for company in companies
        }
