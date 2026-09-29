/* Agent A 文档页导航高亮 */
(function () {
  const links = Array.from(document.querySelectorAll(".side-nav nav a"));
  const sections = links
    .map((a) => document.querySelector(a.getAttribute("href")))
    .filter(Boolean);

  function sync() {
    const y = window.scrollY + 130;
    let current = sections[0];
    for (const section of sections) {
      if (section.offsetTop <= y) current = section;
    }
    links.forEach((link) => {
      const on = current && link.getAttribute("href") === `#${current.id}`;
      link.classList.toggle("active", Boolean(on));
    });
  }

  window.addEventListener("scroll", sync, { passive: true });
  sync();
})();
