import Link from "next/link";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/sources", label: "Sources" },
  { href: "/model", label: "Model" },
  { href: "/about", label: "About" },
];

export default function Masthead({ current }: { current: string }) {
  return (
    <header className="masthead">
      <Link href="/" className="masthead-title">
        Mass Shooting Counts, United States
      </Link>
      <nav>
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            aria-current={item.href === current ? "page" : undefined}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
